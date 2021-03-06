# Copyright 2012-2017, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Helper functions for our test framework.

::

  get_unit_tests - provides our unit tests
  get_integ_tests - provides our integration tests

  get_prereq - provides the tor version required to run the given target
  get_torrc_entries - provides the torrc entries for a given target

Sets of :class:`~test.util.Task` instances can be ran with
:func:`~test.util.run_tasks`. Functions that are intended for easy use with
Tasks are...

::

  Initialization
  |- check_stem_version - checks our version of stem
  |- check_tor_version - checks our version of tor
  |- check_python_version - checks our version of python
  |- check_cryptography_version - checks our version of cryptography
  |- check_pynacl_version - checks our version of pynacl
  |- check_pyflakes_version - checks our version of pyflakes
  |- check_pycodestyle_version - checks our version of pycodestyle
  |- clean_orphaned_pyc - removes any *.pyc without a corresponding *.py
  +- check_for_unused_tests - checks to see if any tests are missing from our settings

Lastly, this module provides generally useful test helpers...

::

  Test Requirements
  |- only_run_once - skip test if it has been ran before
  |- require - skips the test unless a requirement is met
  |
  |- require_cryptography - skips test unless the cryptography module is present
  |- require_pynacl - skips test unless the pynacl module is present
  |- require_command - requires a command to be on the path
  |- require_proc - requires the platform to have recognized /proc contents
  |
  |- require_controller - skips test unless tor provides a controller endpoint
  |- require_version - skips test unless we meet a tor version requirement
  |- require_ptrace - requires 'DisableDebuggerAttachment' to be set
  +- require_online - skips unless targets allow for online tests

  get_message - provides a ControlMessage instance
  get_protocolinfo_response - provides a ProtocolInfoResponse instance
  get_all_combinations - provides all combinations of attributes
  random_fingerprint - provides a random relay fingerprint
  tor_version - provides the version of tor we're testing against
"""

import hashlib
import itertools
import re
import os
import sys
import time

import stem
import stem.prereq
import stem.util.conf
import stem.util.system
import stem.util.test_tools
import stem.version

import test.output

from test.output import STATUS, ERROR, NO_NL, println

CONFIG = stem.util.conf.config_dict('test', {
  'target.prereq': {},
  'target.torrc': {},
  'integ.test_directory': './test/data',
  'test.unit_tests': '',
  'test.integ_tests': '',
})

# Integration targets fall into two categories:
#
# * Run Targets (like RUN_COOKIE and RUN_PTRACE) which customize our torrc.
#   We do an integration test run for each run target we get.
#
# * Attribute Target (like CHROOT and ONLINE) which indicates
#   non-configuration changes to your test runs. These are applied to all
#   integration runs that we perform.

Target = stem.util.enum.UppercaseEnum(
  'ONLINE',
  'RELATIVE',
  'CHROOT',
  'RUN_NONE',
  'RUN_OPEN',
  'RUN_PASSWORD',
  'RUN_COOKIE',
  'RUN_MULTIPLE',
  'RUN_SOCKET',
  'RUN_SCOOKIE',
  'RUN_PTRACE',
  'RUN_ALL',
)

TOR_VERSION = None
RAN_TESTS = []

# We make some paths relative to stem's base directory (the one above us)
# rather than the process' cwd. This doesn't end with a slash.

STEM_BASE = os.path.sep.join(__file__.split(os.path.sep)[:-2])

# Store new capabilities (events, descriptor entries, etc.)

NEW_CAPABILITIES = []
NEW_CAPABILITIES_SUPPRESSION_TOKENS = set()

# File extensions of contents that should be ignored.

IGNORED_FILE_TYPES = []

with open(os.path.join(STEM_BASE, '.gitignore')) as ignore_file:
  for line in ignore_file:
    if line.startswith('*.'):
      IGNORED_FILE_TYPES.append(line[2:].strip())


def get_unit_tests(module_prefix = None):
  """
  Provides the classes for our unit tests.

  :param str module_prefix: only provide the test if the module starts with
    this substring

  :returns: an **iterator** for our unit tests
  """

  if module_prefix and not module_prefix.startswith('test.unit.'):
    module_prefix = 'test.unit.' + module_prefix

  return _get_tests(CONFIG['test.unit_tests'].splitlines(), module_prefix)


def get_integ_tests(module_prefix = None):
  """
  Provides the classes for our integration tests.

  :param str module_prefix: only provide the test if the module starts with
    this substring

  :returns: an **iterator** for our integration tests
  """

  if module_prefix and not module_prefix.startswith('test.integ.'):
    module_prefix = 'test.integ.' + module_prefix

  return _get_tests(CONFIG['test.integ_tests'].splitlines(), module_prefix)


def _get_tests(modules, module_prefix):
  for import_name in modules:
    if import_name:
      module, module_name = import_name.rsplit('.', 1)  # example: util.conf.TestConf

      if not module_prefix or module.startswith(module_prefix):
        yield import_name
      elif module_prefix.startswith(module):
        # single test for this module

        test_module = module_prefix.rsplit('.', 1)[1]
        yield '%s.%s' % (import_name, test_module)


def get_prereq(target):
  """
  Provides the tor version required to run the given target. If the target
  doesn't have any prerequisite then this provides **None**.

  :param Target target: target to provide the prerequisite for

  :returns: :class:`~stem.version.Version` required to run the given target, or
    **None** if there is no prerequisite
  """

  target_prereq = CONFIG['target.prereq'].get(target)

  if target_prereq:
    return stem.version.Requirement[target_prereq]
  else:
    return None


def get_torrc_entries(target):
  """
  Provides the torrc entries used to run the given target.

  :param Target target: target to provide the custom torrc contents of

  :returns: list of :class:`~test.runner.Torrc` entries for the given target

  :raises: **ValueError** if the target.torrc config has entries that don't map
    to test.runner.Torrc
  """

  # converts the 'target.torrc' csv into a list of test.runner.Torrc enums

  config_csv = CONFIG['target.torrc'].get(target)
  torrc_opts = []

  if config_csv:
    for opt in config_csv.split(','):
      opt = opt.strip()

      if opt in test.runner.Torrc.keys():
        torrc_opts.append(test.runner.Torrc[opt])
      else:
        raise ValueError("'%s' isn't a test.runner.Torrc enumeration" % opt)

  return torrc_opts


def get_new_capabilities():
  """
  Provides a list of capabilities tor supports but stem doesn't, as discovered
  while running our tests.

  :returns: **list** of (type, message) tuples for the capabilities
  """

  return NEW_CAPABILITIES


def only_run_once(func):
  """
  Skips the test if it has ran before. If it hasn't then flags it as being ran.
  This is useful to prevent lengthy tests that are independent of integ targets
  from being run repeatedly with ``RUN_ALL``.
  """

  def wrapped(self, *args, **kwargs):
    if self.id() not in RAN_TESTS:
      RAN_TESTS.append(self.id())
      return func(self, *args, **kwargs)
    else:
      self.skipTest('(already ran)')

  return wrapped


def require(condition, message):
  """
  Skips teh test unless the conditional evaluates to 'true'.
  """

  def decorator(func):
    def wrapped(self, *args, **kwargs):
      if condition():
        return func(self, *args, **kwargs)
      else:
        self.skipTest('(%s)' % message)

    return wrapped

  return decorator


require_cryptography = require(stem.prereq.is_crypto_available, 'requires cryptography')
require_pynacl = require(stem.prereq._is_pynacl_available, 'requires pynacl module')
require_proc = require(stem.util.proc.is_available, 'proc unavailable')


def require_controller(func):
  """
  Skips the test unless tor provides an endpoint for controllers to attach to.
  """

  def wrapped(self, *args, **kwargs):
    if test.runner.get_runner().is_accessible():
      return func(self, *args, **kwargs)
    else:
      self.skipTest('(no connection)')

  return wrapped


def require_command(cmd):
  """
  Skips the test unless a command is available on the path.
  """

  return require(lambda: stem.util.system.is_available(cmd), '%s unavailable' % cmd)


def require_version(req_version):
  """
  Skips the test unless we meet the required version.

  :param stem.version.Version req_version: required tor version for the test
  """

  return require(lambda: tor_version() >= req_version, 'requires %s' % req_version)


def require_online(func):
  """
  Skips the test if we weren't started with the ONLINE target, which indicates
  that tests requiring network connectivity should run.
  """

  def wrapped(self, *args, **kwargs):
    if Target.ONLINE in test.runner.get_runner().attribute_targets:
      return func(self, *args, **kwargs)
    else:
      self.skipTest('(requires online target)')

  return wrapped


def check_stem_version():
  return stem.__version__


def check_tor_version(tor_path):
  global TOR_VERSION

  if TOR_VERSION is None:
    TOR_VERSION = stem.version.get_system_tor_version(tor_path)

  return str(TOR_VERSION).split()[0]


def check_python_version():
  return '.'.join(map(str, sys.version_info[:3]))


def check_cryptography_version():
  if stem.prereq.is_crypto_available():
    import cryptography
    return cryptography.__version__
  else:
    return 'missing'


def check_pynacl_version():
  if stem.prereq._is_pynacl_available():
    import nacl
    return nacl.__version__
  else:
    return 'missing'


def check_mock_version():
  if stem.prereq.is_mock_available():
    try:
      import unittest.mock as mock
    except ImportError:
      import mock

    return mock.__version__
  else:
    return 'missing'


def check_pyflakes_version():
  try:
    import pyflakes
    return pyflakes.__version__
  except ImportError:
    return 'missing'


def check_pycodestyle_version():
  if stem.util.test_tools._module_exists('pycodestyle'):
    import pycodestyle
  elif stem.util.test_tools._module_exists('pep8'):
    import pep8 as pycodestyle
  else:
    return 'missing'

  return pycodestyle.__version__


def clean_orphaned_pyc(paths):
  """
  Deletes any file with a *.pyc extention without a corresponding *.py.

  :param list paths: paths to search for orphaned pyc files
  """

  return ['removed %s' % path for path in stem.util.test_tools.clean_orphaned_pyc(paths)]


def check_for_unused_tests(paths):
  """
  The 'test.unit_tests' and 'test.integ_tests' in our settings.cfg defines the
  tests that we run. We do it this way so that we can control the order in
  which our tests are run but there's a disadvantage: when we add new test
  modules we can easily forget to add it there.

  Checking to see if we have any unittest.TestCase subclasses not covered by
  our settings.

  :param list paths: paths to search for unused tests
  """

  unused_tests = []

  for path in paths:
    for py_path in stem.util.system.files_with_suffix(path, '.py'):
      if _is_test_data(py_path):
        continue

      with open(py_path) as f:
        file_contents = f.read()

      test_match = re.search('^class (\S*)\(unittest.TestCase\):$', file_contents, re.MULTILINE)

      if test_match:
        class_name = test_match.groups()[0]
        module_name = py_path.replace(os.path.sep, '.')[len(STEM_BASE) + 1:-3] + '.' + class_name

        if not (module_name in CONFIG['test.unit_tests'] or module_name in CONFIG['test.integ_tests']):
          unused_tests.append(module_name)

  if unused_tests:
    raise ValueError('Test modules are missing from our test/settings.cfg:\n%s' % '\n'.join(unused_tests))


def register_new_capability(capability_type, msg, suppression_token = None):
  """
  Register new capability found during the tests.

  :param str capability_type: type of capability this is
  :param str msg: description of what we found
  :param str suppression_token: skip registration if this token's already been
    provided
  """

  if suppression_token not in NEW_CAPABILITIES_SUPPRESSION_TOKENS:
    NEW_CAPABILITIES.append((capability_type, msg))

    if suppression_token:
      NEW_CAPABILITIES_SUPPRESSION_TOKENS.add(suppression_token)


def _is_test_data(path):
  return os.path.normpath(CONFIG['integ.test_directory']) in path


def run_tasks(category, *tasks):
  """
  Runs a series of :class:`test.util.Task` instances. This simply prints 'done'
  or 'failed' for each unless we fail one that is marked as being required. If
  that happens then we print its error message and call sys.exit().

  :param str category: label for the series of tasks
  :param list tasks: **Task** instances to be ran
  """

  test.output.print_divider(category, True)

  for task in tasks:
    if task is None:
      continue

    task.run()

    if task.is_required and task.error:
      println('\n%s\n' % task.error, ERROR)
      sys.exit(1)

  println()


def get_all_combinations(attr, include_empty = False):
  """
  Provides an iterator for all combinations of a set of attributes. For
  instance...

  ::

    >>> list(test.mocking.get_all_combinations(['a', 'b', 'c']))
    [('a',), ('b',), ('c',), ('a', 'b'), ('a', 'c'), ('b', 'c'), ('a', 'b', 'c')]

  :param list attr: attributes to provide combinations for
  :param bool include_empty: includes an entry with zero items if True
  :returns: iterator for all combinations
  """

  # Makes an itertools.product() call for 'i' copies of attr...
  #
  # * itertools.product(attr) => all one-element combinations
  # * itertools.product(attr, attr) => all two-element combinations
  # * ... etc

  if include_empty:
    yield ()

  seen = set()
  for index in range(1, len(attr) + 1):
    product_arg = [attr for _ in range(index)]

    for item in itertools.product(*product_arg):
      # deduplicate, sort, and only provide if we haven't seen it yet
      item = tuple(sorted(set(item)))

      if item not in seen:
        seen.add(item)
        yield item


def random_fingerprint():
  """
  Provides a random relay fingerprint.
  """

  return hashlib.sha1(os.urandom(20)).hexdigest().upper()


def get_message(content, reformat = True):
  """
  Provides a ControlMessage with content modified to be parsable. This makes
  the following changes unless 'reformat' is false...

  * ensures the content ends with a newline
  * newlines are replaced with a carriage return and newline pair

  :param str content: base content for the controller message
  :param str reformat: modifies content to be more accommodating to being parsed

  :returns: stem.response.ControlMessage instance
  """

  if reformat:
    if not content.endswith('\n'):
      content += '\n'

    content = re.sub('([\r]?)\n', '\r\n', content)

  return stem.response.ControlMessage.from_str(content)


def get_protocolinfo_response(**attributes):
  """
  Provides a ProtocolInfoResponse, customized with the given attributes. The
  base instance is minimal, with its version set to one and everything else
  left with the default.

  :param dict attributes: attributes to customize the response with

  :returns: stem.response.protocolinfo.ProtocolInfoResponse instance
  """

  protocolinfo_response = get_message('250-PROTOCOLINFO 1\n250 OK')
  stem.response.convert('PROTOCOLINFO', protocolinfo_response)

  for attr in attributes:
    setattr(protocolinfo_response, attr, attributes[attr])

  return protocolinfo_response


def tor_version():
  """
  Provides the version of tor we're testing against.

  :returns: :class:`~stem.version.Version` of tor invoked by our integration
    tests

  :raise: **ValueError** if :func:`~test.util.check_tor_version` isn't called
    first
  """

  if TOR_VERSION is None:
    raise ValueError('BUG: check_tor_version() must be called before tor_version()')

  return TOR_VERSION


class Task(object):
  """
  Task we can process while running our tests. The runner can return either a
  message or list of strings for its results.
  """

  def __init__(self, label, runner, args = None, is_required = True, print_result = True, print_runtime = False):
    super(Task, self).__init__()

    self.label = label
    self.runner = runner
    self.args = args
    self.is_required = is_required
    self.print_result = print_result
    self.print_runtime = print_runtime
    self.error = None

    self.is_successful = False
    self.result = None

  def run(self):
    start_time = time.time()
    println('  %s...' % self.label, STATUS, NO_NL)

    padding = 50 - len(self.label)
    println(' ' * padding, NO_NL)

    try:
      if self.args:
        self.result = self.runner(*self.args)
      else:
        self.result = self.runner()

      self.is_successful = True
      output_msg = 'done'

      if self.print_result and isinstance(self.result, str):
        output_msg = self.result
      elif self.print_runtime:
        output_msg += ' (%0.1fs)' % (time.time() - start_time)

      println(output_msg, STATUS)

      if self.print_result and isinstance(self.result, (list, tuple)):
        for line in self.result:
          println('    %s' % line, STATUS)
    except Exception as exc:
      output_msg = str(exc)

      if not output_msg or self.is_required:
        output_msg = 'failed'

      println(output_msg, ERROR)
      self.error = exc


import test.runner  # needs to be imported at the end to avoid a circular dependency

require_ptrace = require(test.runner.get_runner().is_ptraceable, 'DisableDebuggerAttachment is set')
