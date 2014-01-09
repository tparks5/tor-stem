# Copyright 2012-2014, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Helper functions for our test framework.

::

  get_unit_tests - provides our unit tests
  get_integ_tests - provides our integration tests

  is_pyflakes_available - checks if pyflakes is available
  is_pep8_available - checks if pep8 is available

  get_prereq - provides the tor version required to run the given target
  get_torrc_entries - provides the torrc entries for a given target
  get_help_message - provides usage information for running our tests
  get_python3_destination - location where a python3 copy of stem is exported to
  get_stylistic_issues - checks for PEP8 and other stylistic issues
  get_pyflakes_issues - static checks for problems via pyflakes

Sets of :class:`~test.util.Task` instances can be ran with
:func:`~test.util.run_tasks`. Functions that are intended for easy use with
Tasks are...

::

  Initialization
  |- check_stem_version - checks our version of stem
  |- check_python_version - checks our version of python
  |- check_pycrypto_version - checks our version of pycrypto
  |- check_pyflakes_version - checks our version of pyflakes
  |- check_pep8_version - checks our version of pep8
  |- clean_orphaned_pyc - removes any *.pyc without a corresponding *.py
  +- check_for_unused_tests - checks to see if any tests are missing from our settings

  Testing Python 3
  |- python3_prereq - checks that we have python3 and 2to3
  |- python3_clean - deletes our prior python3 export
  |- python3_copy_stem - copies our codebase and converts with 2to3
  +- python3_run_tests - runs python 3 tests
"""

import re
import os
import shutil
import sys

import stem
import stem.prereq
import stem.util.conf
import stem.util.system
import stem.version

import test.output

from test.output import STATUS, ERROR, NO_NL, println

CONFIG = stem.util.conf.config_dict("test", {
  "msg.help": "",
  "target.description": {},
  "target.prereq": {},
  "target.torrc": {},
  "pep8.ignore": [],
  "pyflakes.ignore": [],
  "integ.test_directory": "./test/data",
  "test.unit_tests": "",
  "test.integ_tests": "",
})

Target = stem.util.enum.UppercaseEnum(
  "ONLINE",
  "RELATIVE",
  "CHROOT",
  "RUN_NONE",
  "RUN_OPEN",
  "RUN_PASSWORD",
  "RUN_COOKIE",
  "RUN_MULTIPLE",
  "RUN_SOCKET",
  "RUN_SCOOKIE",
  "RUN_PTRACE",
  "RUN_ALL",
)

# We make some paths relative to stem's base directory (the one above us)
# rather than the process' cwd. This doesn't end with a slash.

STEM_BASE = os.path.sep.join(__file__.split(os.path.sep)[:-2])


def get_unit_tests(module_substring = None):
  """
  Provides the classes for our unit tests.

  :param str module_substring: only provide the test if the module includes this substring

  :returns: an **iterator** for our unit tests
  """

  return _get_tests(CONFIG["test.unit_tests"].splitlines(), module_substring)


def get_integ_tests(module_substring = None):
  """
  Provides the classes for our integration tests.

  :param str module_substring: only provide the test if the module includes this substring

  :returns: an **iterator** for our integration tests
  """

  return _get_tests(CONFIG["test.integ_tests"].splitlines(), module_substring)


def _get_tests(modules, module_substring):
  for import_name in modules:
    if import_name:
      if module_substring and module_substring not in import_name:
        continue

      # Dynamically imports test modules. The __import__() call has a couple
      # quirks that make this a little clunky...
      #
      #   * it only accepts modules, not the actual class we want to import
      #
      #   * it returns the top level module, so we need to transverse into it
      #     for the test class

      module_name = '.'.join(import_name.split('.')[:-1])
      module = __import__(module_name)

      for subcomponent in import_name.split(".")[1:]:
        module = getattr(module, subcomponent)

      yield module


def get_help_message():
  """
  Provides usage information, as provided by the '--help' argument. This
  includes a listing of the valid integration targets.

  :returns: **str** with our usage information
  """

  help_msg = CONFIG["msg.help"]

  # gets the longest target length so we can show the entries in columns
  target_name_length = max(map(len, Target))
  description_format = "\n    %%-%is - %%s" % target_name_length

  for target in Target:
    help_msg += description_format % (target, CONFIG["target.description"].get(target, ""))

  help_msg += "\n"

  return help_msg


def is_pyflakes_available():
  """
  Checks if pyflakes is availalbe.

  :returns: **True** if we can use pyflakes and **False** otherwise
  """

  try:
    import pyflakes.api
    import pyflakes.reporter
    return True
  except ImportError:
    return False


def is_pep8_available():
  """
  Checks if pep8 is availalbe.

  :returns: **True** if we can use pep8 and **False** otherwise
  """

  try:
    import pep8

    if not hasattr(pep8, 'BaseReport'):
      raise ImportError()

    return True
  except ImportError:
    return False


def get_prereq(target):
  """
  Provides the tor version required to run the given target. If the target
  doesn't have any prerequisite then this provides **None**.

  :param Target target: target to provide the prerequisite for

  :returns: :class:`~stem.version.Version` required to run the given target, or
    **None** if there is no prerequisite
  """

  target_prereq = CONFIG["target.prereq"].get(target)

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

  config_csv = CONFIG["target.torrc"].get(target)
  torrc_opts = []

  if config_csv:
    for opt in config_csv.split(','):
      opt = opt.strip()

      if opt in test.runner.Torrc.keys():
        torrc_opts.append(test.runner.Torrc[opt])
      else:
        raise ValueError("'%s' isn't a test.runner.Torrc enumeration" % opt)

  return torrc_opts


def get_python3_destination():
  """
  Provides the location where a python 3 copy of stem is exported to for
  testing.

  :returns: **str** with the relative path to our python 3 location
  """

  return os.path.join(CONFIG["integ.test_directory"], "python3")


def get_stylistic_issues(paths):
  """
  Checks for stylistic issues that are an issue according to the parts of PEP8
  we conform to. This alsochecks a few other stylistic issues:

  * two space indentations
  * tabs are the root of all evil and should be shot on sight
  * standard newlines (\\n), not windows (\\r\\n) nor classic mac (\\r)
  * checks that we're using 'as' for exceptions rather than a comma

  :param list paths: paths to search for stylistic issues

  :returns: **dict** of the form ``path => [(line_number, message)...]``
  """

  issues = {}

  if is_pep8_available():
    import pep8

    class StyleReport(pep8.BaseReport):
      def __init__(self, options):
        super(StyleReport, self).__init__(options)

      def error(self, line_number, offset, text, check):
        code = super(StyleReport, self).error(line_number, offset, text, check)

        if code:
          issues.setdefault(self.filename, []).append((offset + line_number, "%s %s" % (code, text)))

    style_checker = pep8.StyleGuide(ignore = CONFIG["pep8.ignore"], reporter = StyleReport)
    style_checker.check_files(list(_python_files(paths)))

  for path in _python_files(paths):
    with open(path) as f:
      file_contents = f.read()

    lines, prev_indent = file_contents.split("\n"), 0
    is_block_comment = False

    for index, line in enumerate(lines):
      whitespace, content = re.match("^(\s*)(.*)$", line).groups()

      # TODO: This does not check that block indentations are two spaces
      # because differentiating source from string blocks ("""foo""") is more
      # of a pita than I want to deal with right now.

      if '"""' in content:
        is_block_comment = not is_block_comment

      if "\t" in whitespace:
        issues.setdefault(path, []).append((index + 1, "indentation has a tab"))
      elif "\r" in content:
        issues.setdefault(path, []).append((index + 1, "contains a windows newline"))
      elif content != content.rstrip():
        issues.setdefault(path, []).append((index + 1, "line has trailing whitespace"))
      elif content.lstrip().startswith("except") and content.endswith(", exc:"):
        # Python 2.6 - 2.7 supports two forms for exceptions...
        #
        #   except ValueError, exc:
        #   except ValueError as exc:
        #
        # The former is the old method and no longer supported in python 3
        # going forward.

        issues.setdefault(path, []).append((index + 1, "except clause should use 'as', not comma"))

  return issues


def get_pyflakes_issues(paths):
  """
  Performs static checks via pyflakes.

  :param list paths: paths to search for problems

  :returns: dict of the form ``path => [(line_number, message)...]``
  """

  issues = {}

  if is_pyflakes_available():
    import pyflakes.api
    import pyflakes.reporter

    class Reporter(pyflakes.reporter.Reporter):
      def __init__(self):
        self._ignored_issues = {}

        for line in CONFIG["pyflakes.ignore"]:
          path, issue = line.split("=>")
          self._ignored_issues.setdefault(path.strip(), []).append(issue.strip())

      def unexpectedError(self, filename, msg):
        self._register_issue(filename, None, msg)

      def syntaxError(self, filename, msg, lineno, offset, text):
        self._register_issue(filename, lineno, msg)

      def flake(self, msg):
        self._register_issue(msg.filename, msg.lineno, msg.message % msg.message_args)

      def _is_ignored(self, path, issue):
        # Paths in pyflakes_ignore are relative, so we need to check to see if our
        # path ends with any of them.

        for ignored_path, ignored_issues in self._ignored_issues.items():
          if path.endswith(ignored_path) and issue in ignored_issues:
            return True

        return False

      def _register_issue(self, path, line_number, issue):
        if not self._is_ignored(path, issue):
          issues.setdefault(path, []).append((line_number, issue))

    reporter = Reporter()

    for path in _python_files(paths):
      pyflakes.api.checkPath(path, reporter)

  return issues


def check_stem_version():
  return stem.__version__


def check_python_version():
  return '.'.join(map(str, sys.version_info[:3]))


def check_pycrypto_version():
  if stem.prereq.is_crypto_available():
    import Crypto
    return Crypto.__version__
  else:
    return "missing"


def check_mock_version():
  if stem.prereq.is_mock_available():
    try:
      import unittest.mock as mock
    except ImportError:
      import mock

    return mock.__version__
  else:
    return "missing"


def check_pyflakes_version():
  try:
    import pyflakes
    return pyflakes.__version__
  except ImportError:
    return "missing"


def check_pep8_version():
  try:
    import pep8
    return pep8.__version__
  except ImportError:
    return "missing"


def clean_orphaned_pyc(paths):
  """
  Deletes any file with a *.pyc extention without a corresponding *.py. This
  helps to address a common gotcha when deleting python files...

  * You delete module 'foo.py' and run the tests to ensure that you haven't
    broken anything. They pass, however there *are* still some 'import foo'
    statements that still work because the bytecode (foo.pyc) is still around.

  * You push your change.

  * Another developer clones our repository and is confused because we have a
    bunch of ImportErrors.

  :param list paths: paths to search for orphaned pyc files
  """

  orphaned_pyc = []

  for path in paths:
    for pyc_path in stem.util.system.files_with_suffix(path, '.pyc'):
      # If we're running python 3 then the *.pyc files are no longer bundled
      # with the *.py. Rather, they're in a __pycache__ directory.
      #
      # At the moment there's no point in checking for orphaned bytecode with
      # python 3 because it's an exported copy of the python 2 codebase, so
      # skipping.

      if "__pycache__" in pyc_path:
        continue

      if not os.path.exists(pyc_path[:-1]):
        orphaned_pyc.append(pyc_path)
        os.remove(pyc_path)

  return ["removed %s" % path for path in orphaned_pyc]


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

      test_match = re.search("^class (\S*)\(unittest.TestCase\):$", file_contents, re.MULTILINE)

      if test_match:
        class_name = test_match.groups()[0]
        module_name = py_path.replace(os.path.sep, '.')[len(STEM_BASE) + 1:-3] + '.' + class_name

        if not (module_name in CONFIG['test.unit_tests'] or module_name in CONFIG['test.integ_tests']):
          unused_tests.append(module_name)

  if unused_tests:
    raise ValueError("Test modules are missing from our test/settings.cfg:\n%s" % "\n".join(unused_tests))


def python3_prereq():
  for required_cmd in ("2to3", "python3"):
    if not stem.util.system.is_available(required_cmd):
      raise ValueError("Unable to test python 3 because %s isn't in your path" % required_cmd)


def python3_clean(skip = False):
  location = get_python3_destination()

  if not os.path.exists(location):
    return "skipped"
  elif skip:
    return ["Reusing '%s'. Run again with '--clean' if you want a fresh copy." % location]
  else:
    shutil.rmtree(location, ignore_errors = True)
    return "done"


def python3_copy_stem():
  destination = get_python3_destination()

  if os.path.exists(destination):
    return "skipped"

  # skips the python3 destination (to avoid an infinite loop)
  def _ignore(src, names):
    if src == os.path.normpath(destination):
      return names
    else:
      return []

  os.makedirs(destination)
  shutil.copytree('stem', os.path.join(destination, 'stem'))
  shutil.copytree('test', os.path.join(destination, 'test'), ignore = _ignore)
  shutil.copy('run_tests.py', os.path.join(destination, 'run_tests.py'))
  stem.util.system.call("2to3 --write --nobackups --no-diffs %s" % get_python3_destination())

  return "done"


def python3_run_tests():
  println()
  println()

  python3_runner = os.path.join(get_python3_destination(), "run_tests.py")
  exit_status = os.system("python3 %s %s" % (python3_runner, " ".join(sys.argv[1:])))
  sys.exit(exit_status)


def _is_test_data(path):
  return os.path.normpath(CONFIG["integ.test_directory"]) in path


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
      println("\n%s\n" % task.error, ERROR)
      sys.exit(1)

  println()


def _python_files(paths):
  for path in paths:
    for file_path in stem.util.system.files_with_suffix(path, '.py'):
      if not _is_test_data(file_path):
        yield file_path


class Task(object):
  """
  Task we can process while running our tests. The runner can return either a
  message or list of strings for its results.
  """

  def __init__(self, label, runner, args = None, is_required = True, print_result = True):
    super(Task, self).__init__()

    self.label = label
    self.runner = runner
    self.args = args
    self.is_required = is_required
    self.print_result = print_result
    self.error = None

    self.is_successful = False
    self.result = None

  def run(self):
    println("  %s..." % self.label, STATUS, NO_NL)

    padding = 50 - len(self.label)
    println(" " * padding, NO_NL)

    try:
      if self.args:
        self.result = self.runner(*self.args)
      else:
        self.result = self.runner()

      self.is_successful = True
      output_msg = "done"

      if self.print_result and isinstance(self.result, str):
        output_msg = self.result

      println(output_msg, STATUS)

      if self.print_result and isinstance(self.result, (list, tuple)):
        for line in self.result:
          println("    %s" % line, STATUS)
    except Exception as exc:
      output_msg = str(exc)

      if not output_msg or self.is_required:
        output_msg = "failed"

      println(output_msg, ERROR)
      self.error = exc
