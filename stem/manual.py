# Copyright 2015, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Information available about Tor from `its manual
<https://www.torproject.org/docs/tor-manual.html.en>`_. This provides three
methods of getting this information...

* :func:`~stem.manual.Manual.from_cache` provides manual content bundled with
  Stem. This is the fastest and most reliable method but only as up-to-date as
  Stem's release.

* :func:`~stem.manual.Manual.from_man` reads Tor's local man page for
  information about it.

* :func:`~stem.manual.Manual.from_remote` fetches the latest manual information
  remotely. This is the slowest and least reliable method but provides the most
  recent information about Tor.

Manual information includes arguments, signals, and probably most usefully the
torrc configuration options. For example, say we want a little script that told
us what our torrc options do...

.. literalinclude::  /_static/example/manual_config_options.py
   :language: python

|

.. image:: /_static/manual_output.png

|

**Module Overview:**

::

  is_important - Indicates if a configuration option is of particularly common importance.
  download_man_page - Downloads tor's latest man page.

  Manual - Information about Tor available from its manual.
   | |- from_cache - Provides manual information cached with Stem.
   | |- from_man - Retrieves manual information from its man page.
   | +- from_remote - Retrieves manual information remotely from tor's latest manual.
   |
   +- save - writes the manual contents to a given location

.. versionadded:: 1.5.0
"""

import collections
import os
import shutil
import sys
import tempfile

import stem.prereq
import stem.util.conf
import stem.util.enum
import stem.util.log
import stem.util.system

try:
  # added in python 2.7
  from collections import OrderedDict
except ImportError:
  from stem.util.ordereddict import OrderedDict

try:
  # added in python 3.2
  from functools import lru_cache
except ImportError:
  from stem.util.lru_cache import lru_cache

try:
  # account for urllib's change between python 2.x and 3.x
  import urllib.request as urllib
except ImportError:
  import urllib2 as urllib

Category = stem.util.enum.Enum('GENERAL', 'CLIENT', 'RELAY', 'DIRECTORY', 'AUTHORITY', 'HIDDEN_SERVICE', 'TESTING', 'UNKNOWN')
GITWEB_MANUAL_URL = 'https://gitweb.torproject.org/tor.git/plain/doc/tor.1.txt'
CACHE_PATH = os.path.join(os.path.dirname(__file__), 'cached_tor_manual')

CATEGORY_SECTIONS = {
  'GENERAL OPTIONS': Category.GENERAL,
  'CLIENT OPTIONS': Category.CLIENT,
  'SERVER OPTIONS': Category.RELAY,
  'DIRECTORY SERVER OPTIONS': Category.DIRECTORY,
  'DIRECTORY AUTHORITY SERVER OPTIONS': Category.AUTHORITY,
  'HIDDEN SERVICE OPTIONS': Category.HIDDEN_SERVICE,
  'TESTING NETWORK OPTIONS': Category.TESTING,
}


class ConfigOption(collections.namedtuple('ConfigOption', ['category', 'name', 'usage', 'summary', 'description'])):
  """
  Tor configuration attribute found in its torrc.

  :var stem.manual.Category category: category the config option was listed
    under, this is Category.UNKNOWN if we didn't recognize the category
  :var str name: name of the configuration option
  :var str usage: arguments accepted by the option
  :var str summary: brief description of what the option does
  :var str description: longer manual description with details
  """


@lru_cache()
def _config(lowercase = True):
  """
  Provides a dictionary for our settings.cfg. This has a couple categories...

    * manual.important (list) - configuration options considered to be important
    * manual.summary.* (str) - summary descriptions of config options

  :param bool lowercase: uses lowercase keys if **True** to allow for case
    insensitive lookups
  """

  config = stem.util.conf.Config()
  config_path = os.path.join(os.path.dirname(__file__), 'settings.cfg')

  try:
    config.load(config_path)
    config_dict = dict([(key.lower() if lowercase else key, config.get_value(key)) for key in config.keys()])
    config_dict['manual.important'] = [name.lower() if lowercase else name for name in config.get_value('manual.important', [], multiple = True)]
    return config_dict
  except Exception as exc:
    stem.util.log.warn("BUG: stem failed to load its internal manual information from '%s': %s" % (config_path, exc))
    return {}


def is_important(option):
  """
  Indicates if a configuration option of particularly common importance or not.

  :param str option: tor configuration option to check

  :returns: **bool** that's **True** if this is an important option and
    **False** otherwise
  """

  return option.lower() in _config()['manual.important']


def download_man_page(path = None, file_handle = None, url = GITWEB_MANUAL_URL, timeout = 20):
  """
  Downloads tor's latest man page from `gitweb.torproject.org
  <https://gitweb.torproject.org/tor.git/plain/doc/tor.1.txt>`_. This method is
  both slow and unreliable - please see the warnings on
  :func:`~stem.manual.Manual.from_remote`.

  :param str path: path to save tor's man page to
  :param file file_handle: file handler to save tor's man page to
  :param str url: url to download tor's asciidoc manual from
  :param int timeout: seconds to wait before timing out the request

  :raises: **IOError** if unable to retrieve the manual
  """

  if not path and not file_handle:
    raise ValueError("Either the path or file_handle we're saving to must be provided")
  elif not stem.util.system.is_available('a2x'):
    raise IOError('We require a2x from asciidoc to provide a man page')

  dirpath = tempfile.mkdtemp()
  asciidoc_path = os.path.join(dirpath, 'tor.1.txt')
  manual_path = os.path.join(dirpath, 'tor.1')

  try:
    try:
      with open(asciidoc_path, 'wb') as asciidoc_file:
        request = urllib.urlopen(url, timeout = timeout)
        shutil.copyfileobj(request, asciidoc_file)
    except:
      exc = sys.exc_info()[1]
      raise IOError("Unable to download tor's manual from %s to %s: %s" % (url, asciidoc_path, exc))

    try:
      stem.util.system.call('a2x -f manpage %s' % asciidoc_path)

      if not os.path.exists(manual_path):
        raise OSError('no man page was generated')
    except OSError as exc:
      raise IOError("Unable to run 'a2x -f manpage %s': %s" % (asciidoc_path, exc))

    if path:
      try:
        path_dir = os.path.dirname(path)

        if not os.path.exists(path_dir):
          os.makedirs(path_dir)

        shutil.copyfile(manual_path, path)
      except OSError as exc:
        raise IOError(exc)

    if file_handle:
      with open(manual_path, 'rb') as manual_file:
        shutil.copyfileobj(manual_file, file_handle)
        file_handle.flush()
  finally:
    shutil.rmtree(dirpath)


class Manual(object):
  """
  Parsed tor man page. Tor makes no guarantees about its man page format so
  this may not always be compatible. If not you can use the cached manual
  information stored with Stem.

  This does not include every bit of information from the tor manual. For
  instance, I've excluded the 'THE CONFIGURATION FILE FORMAT' section. If
  there's a part you'd find useful then `file an issue
  <https://trac.torproject.org/projects/tor/wiki/doc/stem/bugs>`_ and we can
  add it.

  :var str name: brief description of the tor command
  :var str synopsis: brief tor command usage
  :var str description: general description of what tor does

  :var dict commandline_options: mapping of commandline arguments to their descripton
  :var dict signals: mapping of signals tor accepts to their description
  :var dict files: mapping of file paths to their description

  :var dict config_options: :class:`~stem.manual.ConfigOption` tuples for tor configuration options

  :var str man_commit: latest tor commit editing the man page when this
    information was cached
  :var str stem_commit: stem commit to cache this manual information
  """

  def __init__(self, name, synopsis, description, commandline_options, signals, files, config_options):
    self.name = name
    self.synopsis = synopsis
    self.description = description
    self.commandline_options = commandline_options
    self.signals = signals
    self.files = files
    self.config_options = config_options
    self.man_commit = None
    self.stem_commit = None

  @staticmethod
  def from_cache(path = None):
    """
    Provides manual information cached with Stem. Unlike
    :func:`~stem.manual.Manual.from_man` and
    :func:`~stem.manual.Manual.from_remote` this doesn't have any system
    requirements, and is faster too. Only drawback is that this manual
    content is only as up to date as the Stem release we're using.

    :param str path: cached manual content to read, if not provided this uses
      the bundled manual information

    :returns: :class:`~stem.manual.Manual` with our bundled manual information

    :raises: **IOError** if a **path** was provided and we were unable to read it
    """

    conf = stem.util.conf.Config()
    conf.load(path if path else CACHE_PATH, commenting = False)

    config_options = OrderedDict()

    for key in conf.keys():
      if key.startswith('config_options.'):
        key = key.split('.')[1]

        if key not in config_options:
          config_options[key] = ConfigOption(
            conf.get('config_options.%s.category' % key, ''),
            conf.get('config_options.%s.name' % key, ''),
            conf.get('config_options.%s.usage' % key, ''),
            conf.get('config_options.%s.summary' % key, ''),
            conf.get('config_options.%s.description' % key, '')
          )

    manual = Manual(
      conf.get('name', ''),
      conf.get('synopsis', ''),
      conf.get('description', ''),
      conf.get('commandline_options', {}),
      conf.get('signals', {}),
      conf.get('files', {}),
      config_options,
    )

    manual.man_commit = conf.get('man_commit', None)
    manual.stem_commit = conf.get('stem_commit', None)

    return manual

  @staticmethod
  def from_man(man_path = 'tor'):
    """
    Reads and parses a given man page.

    :param str man_path: path argument for 'man', for example you might want
      '/path/to/tor/doc/tor.1' to read from tor's git repository

    :returns: :class:`~stem.manual.Manual` for the system's man page

    :raises: **IOError** if unable to retrieve the manual
    """

    try:
      man_output = stem.util.system.call('man --encoding=ascii -P cat %s' % man_path, env = {'MANWIDTH': '10000000'})
    except OSError as exc:
      raise IOError("Unable to run 'man --encoding=ascii -P cat %s': %s" % (man_path, exc))

    categories, config_options = _get_categories(man_output), OrderedDict()

    for category_header, category_enum in CATEGORY_SECTIONS.items():
      _add_config_options(config_options, category_enum, categories.get(category_header, []))

    for category in categories:
      if category.endswith(' OPTIONS') and category not in CATEGORY_SECTIONS and category != 'COMMAND-LINE OPTIONS':
        _add_config_options(config_options, Category.UNKNOWN, categories.get(category, []))

    return Manual(
      _join_lines(categories.get('NAME', [])),
      _join_lines(categories.get('SYNOPSIS', [])),
      _join_lines(categories.get('DESCRIPTION', [])),
      _get_indented_descriptions(categories.get('COMMAND-LINE OPTIONS', [])),
      _get_indented_descriptions(categories.get('SIGNALS', [])),
      _get_indented_descriptions(categories.get('FILES', [])),
      config_options,
    )

  @staticmethod
  def from_remote(timeout = 60):
    """
    Reads and parses the latest tor man page `from gitweb.torproject.org
    <https://gitweb.torproject.org/tor.git/plain/doc/tor.1.txt>`_. Note that
    while convenient, this reliance on GitWeb means you should alway call with
    a fallback, such as...

    ::

      try:
        manual = stem.manual.from_remote()
      except IOError:
        manual = stem.manual.from_cache()

    In addition to our GitWeb dependency this requires 'a2x' which is part of
    `asciidoc <http://asciidoc.org/INSTALL.html>`_ and... isn't quick.
    Personally this takes ~7.41s, breaking down for me as follows...

      * 1.67s to download tor.1.txt
      * 5.57s to convert the asciidoc to a man page
      * 0.17s for stem to read and parse the manual

    :param int timeout: seconds to wait before timing out the request

    :returns: latest :class:`~stem.manual.Manual` available for tor

    :raises: **IOError** if unable to retrieve the manual
    """

    with tempfile.NamedTemporaryFile() as tmp:
      download_man_page(file_handle = tmp, timeout = timeout)
      return Manual.from_man(tmp.name)

  def save(self, path):
    """
    Persists the manual content to a given location.

    :param str path: path to save our manual content to

    :raises: **IOError** if unsuccessful
    """

    conf = stem.util.conf.Config()
    conf.set('name', self.name)
    conf.set('synopsis', self.synopsis)
    conf.set('description', self.description)

    if self.man_commit:
      conf.set('man_commit', self.man_commit)

    if self.stem_commit:
      conf.set('stem_commit', self.stem_commit)

    for k, v in self.commandline_options.items():
      conf.set('commandline_options', '%s => %s' % (k, v), overwrite = False)

    for k, v in self.signals.items():
      conf.set('signals', '%s => %s' % (k, v), overwrite = False)

    for k, v in self.files.items():
      conf.set('files', '%s => %s' % (k, v), overwrite = False)

    for k, v in self.config_options.items():
      conf.set('config_options.%s.category' % k, v.category)
      conf.set('config_options.%s.name' % k, v.name)
      conf.set('config_options.%s.usage' % k, v.usage)
      conf.set('config_options.%s.summary' % k, v.summary)
      conf.set('config_options.%s.description' % k, v.description)

    conf.save(path)

  def __eq__(self, other):
    if not isinstance(other, Manual):
      return False

    for attr in ('name', 'synopsis', 'description', 'commandline_options', 'signals', 'files', 'config_options'):
      if getattr(self, attr) != getattr(other, attr):
        return False

    return True


def _get_categories(content):
  """
  The man page is headers followed by an indented section. First pass gets
  the mapping of category titles to their lines.
  """

  # skip header and footer lines

  if content and 'TOR(1)' in content[0]:
    content = content[1:]

  if content and 'TOR(1)' in content[-1]:
    content = content[:-1]

  categories = {}
  category, lines = None, []

  for line in content:
    # replace non-ascii characters
    #
    #   \u2019 - smart single quote
    #   \u2014 - extra long dash
    #   \xb7 - centered dot

    char_for = chr if stem.prereq.is_python_3() else unichr
    line = line.replace(char_for(0x2019), "'").replace(char_for(0x2014), '-').replace(char_for(0xb7), '*')

    if line and not line.startswith(' '):
      if category:
        if lines[-1] == '':
          lines = lines[:-1]  # sections end with an extra empty line

        categories[category] = lines

      category, lines = line.strip(), []
    else:
      if line.startswith('       '):
        line = line[7:]  # contents of a section have a seven space indentation

      lines.append(line)

  if category:
    categories[category] = lines

  return categories


def _get_indented_descriptions(lines):
  """
  Parses the commandline argument and signal sections. These are options
  followed by an indented description. For example...

  ::

    -f FILE
        Specify a new configuration file to contain further Tor configuration
        options OR pass - to make Tor read its configuration from standard
        input. (Default: /usr/local/etc/tor/torrc, or $HOME/.torrc if that file
        is not found)

  There can be additional paragraphs not related to any particular argument but
  ignoring those.
  """

  options, last_arg = OrderedDict(), None

  for line in lines:
    if line and not line.startswith(' '):
      options[line], last_arg = [], line
    elif last_arg and line.startswith('    '):
      options[last_arg].append(line[4:])

  return dict([(arg, ' '.join(desc_lines)) for arg, desc_lines in options.items() if desc_lines])


def _add_config_options(config_options, category, lines):
  """
  Parses a section of tor configuration options. These have usage information,
  followed by an indented description. For instance...

  ::

    ConnLimit NUM
        The minimum number of file descriptors that must be available to the
        Tor process before it will start. Tor will ask the OS for as many file
        descriptors as the OS will allow (you can find this by "ulimit -H -n").
        If this number is less than ConnLimit, then Tor will refuse to start.


        You probably don't need to adjust this. It has no effect on Windows
        since that platform lacks getrlimit(). (Default: 1000)
  """

  last_option, usage, description = None, None, []

  if lines and lines[0].startswith('The following options'):
    lines = lines[lines.index(''):]  # drop the initial description

  for line in lines:
    if line and not line.startswith(' '):
      if last_option:
        summary = _config().get('manual.summary.%s' % last_option.lower(), '')
        config_options[last_option] = ConfigOption(category, last_option, usage, summary, _join_lines(description).strip())

      if ' ' in line:
        last_option, usage = line.split(' ', 1)
      else:
        last_option, usage = line, ''

      description = []
    else:
      if line.startswith('    '):
        line = line[4:]

      description.append(line)

  if last_option:
    summary = _config().get('manual.summary.%s' % last_option.lower(), '')
    config_options[last_option] = ConfigOption(category, last_option, usage, summary, _join_lines(description).strip())


def _join_lines(lines):
  """
  Simple join, except we want empty lines to still provide a newline.
  """

  result = []

  for line in lines:
    if not line:
      if result and result[-1] != '\n':
        result.append('\n')
    else:
      result.append(line + '\n')

  return ''.join(result).strip()
