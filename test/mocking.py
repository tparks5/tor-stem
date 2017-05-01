# Copyright 2012-2017, Damian Johnson and The Tor Project
# See LICENSE for licensing information

"""
Helper functions for creating mock objects.

::

  get_all_combinations - provides all combinations of attributes
  random_fingerprint - provides a random relay fingerprint

  Instance Constructors
    get_message                     - stem.response.ControlMessage
    get_protocolinfo_response       - stem.response.protocolinfo.ProtocolInfoResponse

    stem.descriptor.networkstatus
      get_directory_authority        - DirectoryAuthority
      get_key_certificate            - KeyCertificate
      get_network_status_document_v2 - NetworkStatusDocumentV2
      get_network_status_document_v3 - NetworkStatusDocumentV3

    stem.descriptor.router_status_entry
      get_router_status_entry_v2       - RouterStatusEntryV2
      get_router_status_entry_v3       - RouterStatusEntryV3
      get_router_status_entry_micro_v3 - RouterStatusEntryMicroV3
"""

import hashlib
import itertools
import os
import re

import stem.descriptor.extrainfo_descriptor
import stem.descriptor.hidden_service_descriptor
import stem.descriptor.microdescriptor
import stem.descriptor.networkstatus
import stem.descriptor.router_status_entry
import stem.descriptor.server_descriptor
import stem.prereq
import stem.response
import stem.util.str_tools

try:
  # added in python 2.7
  from collections import OrderedDict
except ImportError:
  from stem.util.ordereddict import OrderedDict

CRYPTO_BLOB = """
MIGJAoGBAJv5IIWQ+WDWYUdyA/0L8qbIkEVH/cwryZWoIaPAzINfrw1WfNZGtBmg
skFtXhOHHqTRN4GPPrZsAIUOQGzQtGb66IQgT4tO/pj+P6QmSCCdTfhvGfgTCsC+
WPi4Fl2qryzTb3QO5r5x7T8OsG2IBUET1bLQzmtbC560SYR49IvVAgMBAAE=
"""

DOC_SIG = stem.descriptor.networkstatus.DocumentSignature(
  'sha1',
  '14C131DFC5C6F93646BE72FA1401C02A8DF2E8B4',
  'BF112F1C6D5543CFD0A32215ACABD4197B5279AD',
  '-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----' % CRYPTO_BLOB)

ROUTER_STATUS_ENTRY_V2_HEADER = (
  ('r', 'caerSidi p1aag7VwarGxqctS7/fS0y5FU+s oQZFLYe9e4A7bOkWKR7TaNxb0JE 2012-08-06 11:19:31 71.35.150.29 9001 0'),
)

ROUTER_STATUS_ENTRY_V3_HEADER = (
  ('r', 'caerSidi p1aag7VwarGxqctS7/fS0y5FU+s oQZFLYe9e4A7bOkWKR7TaNxb0JE 2012-08-06 11:19:31 71.35.150.29 9001 0'),
  ('s', 'Fast Named Running Stable Valid'),
)

ROUTER_STATUS_ENTRY_MICRO_V3_HEADER = (
  ('r', 'Konata ARIJF2zbqirB9IwsW0mQznccWww 2012-09-24 13:40:40 69.64.48.168 9001 9030'),
  ('m', 'aiUklwBrua82obG5AsTX+iEpkjQA2+AQHxZ7GwMfY70'),
  ('s', 'Fast Guard HSDir Named Running Stable V2Dir Valid'),
)

AUTHORITY_HEADER = (
  ('dir-source', 'turtles 27B6B5996C426270A5C95488AA5BCEB6BCC86956 no.place.com 76.73.17.194 9030 9090'),
  ('contact', 'Mike Perry <email>'),
)

KEY_CERTIFICATE_HEADER = (
  ('dir-key-certificate-version', '3'),
  ('fingerprint', '27B6B5996C426270A5C95488AA5BCEB6BCC86956'),
  ('dir-key-published', '2011-11-28 21:51:04'),
  ('dir-key-expires', '2012-11-28 21:51:04'),
  ('dir-identity-key', '\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----' % CRYPTO_BLOB),
  ('dir-signing-key', '\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----' % CRYPTO_BLOB),
)

KEY_CERTIFICATE_FOOTER = (
  ('dir-key-certification', '\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----' % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_HEADER_V2 = (
  ('network-status-version', '2'),
  ('dir-source', '18.244.0.114 18.244.0.114 80'),
  ('fingerprint', '719BE45DE224B607C53707D0E2143E2D423E74CF'),
  ('contact', 'arma at mit dot edu'),
  ('published', '2005-12-16 00:13:46'),
  ('dir-signing-key', '\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----' % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_FOOTER_V2 = (
  ('directory-signature', 'moria2\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----' % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_HEADER = (
  ('network-status-version', '3'),
  ('vote-status', 'consensus'),
  ('consensus-methods', None),
  ('consensus-method', None),
  ('published', None),
  ('valid-after', '2012-09-02 22:00:00'),
  ('fresh-until', '2012-09-02 22:00:00'),
  ('valid-until', '2012-09-02 22:00:00'),
  ('voting-delay', '300 300'),
  ('client-versions', None),
  ('server-versions', None),
  ('package', None),
  ('known-flags', 'Authority BadExit Exit Fast Guard HSDir Named Running Stable Unnamed V2Dir Valid'),
  ('params', None),
)

NETWORK_STATUS_DOCUMENT_FOOTER = (
  ('directory-footer', ''),
  ('bandwidth-weights', None),
  ('directory-signature', '%s %s\n%s' % (DOC_SIG.identity, DOC_SIG.key_digest, DOC_SIG.signature)),
)


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


def _get_descriptor_content(attr = None, exclude = (), header_template = (), footer_template = ()):
  """
  Constructs a minimal descriptor with the given attributes. The content we
  provide back is of the form...

  * header_template (with matching attr filled in)
  * unused attr entries
  * footer_template (with matching attr filled in)

  So for instance...

  ::

    get_descriptor_content(
      attr = {'nickname': 'caerSidi', 'contact': 'atagar'},
      header_template = (
        ('nickname', 'foobar'),
        ('fingerprint', '12345'),
      ),
    )

  ... would result in...

  ::

    nickname caerSidi
    fingerprint 12345
    contact atagar

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param tuple header_template: key/value pairs for mandatory fields before unrecognized content
  :param tuple footer_template: key/value pairs for mandatory fields after unrecognized content

  :returns: str with the requested descriptor content
  """

  header_content, footer_content = [], []
  attr = {} if attr is None else dict(attr)

  attr = OrderedDict(attr)  # shallow copy since we're destructive

  for content, template in ((header_content, header_template),
                            (footer_content, footer_template)):
    for keyword, value in template:
      if keyword in exclude:
        continue
      elif keyword in attr:
        value = attr[keyword]
        del attr[keyword]

      if value is None:
        continue
      elif value == '':
        content.append(keyword)
      elif keyword == 'onion-key' or keyword == 'signing-key' or keyword == 'router-signature':
        content.append('%s%s' % (keyword, value))
      else:
        content.append('%s %s' % (keyword, value))

  remainder = []

  for k, v in attr.items():
    if v:
      remainder.append('%s %s' % (k, v))
    else:
      remainder.append(k)

  return stem.util.str_tools._to_bytes('\n'.join(header_content + remainder + footer_content))


def get_router_status_entry_v2(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryV2

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: RouterStatusEntryV2 for the requested descriptor content
  """

  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_V2_HEADER)

  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryV2(desc_content, validate = True)


def get_router_status_entry_v3(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryV3

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: RouterStatusEntryV3 for the requested descriptor content
  """

  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_V3_HEADER)

  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryV3(desc_content, validate = True)


def get_router_status_entry_micro_v3(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryMicroV3

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: RouterStatusEntryMicroV3 for the requested descriptor content
  """

  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_MICRO_V3_HEADER)

  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryMicroV3(desc_content, validate = True)


def get_directory_authority(attr = None, exclude = (), is_vote = False, content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.DirectoryAuthority

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool is_vote: True if this is for a vote, False if it's for a consensus
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: DirectoryAuthority for the requested descriptor content
  """

  attr = {} if attr is None else dict(attr)

  if not is_vote:
    # entries from a consensus also have a mandatory 'vote-digest' field
    if not ('vote-digest' in attr or (exclude and 'vote-digest' in exclude)):
      attr['vote-digest'] = '0B6D1E9A300B895AA2D0B427F92917B6995C3C1C'

  desc_content = _get_descriptor_content(attr, exclude, AUTHORITY_HEADER)

  if is_vote:
    desc_content += b'\n' + get_key_certificate(content = True)

  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.DirectoryAuthority(desc_content, validate = True, is_vote = is_vote)


def get_key_certificate(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.KeyCertificate

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: KeyCertificate for the requested descriptor content
  """

  desc_content = _get_descriptor_content(attr, exclude, KEY_CERTIFICATE_HEADER, KEY_CERTIFICATE_FOOTER)

  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.KeyCertificate(desc_content, validate = True)


def get_network_status_document_v2(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.NetworkStatusDocumentV2

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: NetworkStatusDocumentV2 for the requested descriptor content
  """

  desc_content = _get_descriptor_content(attr, exclude, NETWORK_STATUS_DOCUMENT_HEADER_V2, NETWORK_STATUS_DOCUMENT_FOOTER_V2)

  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.NetworkStatusDocumentV2(desc_content, validate = True)


def get_network_status_document_v3(attr = None, exclude = (), authorities = None, routers = None, content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.NetworkStatusDocumentV3

  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param list authorities: directory authorities to include in the document
  :param list routers: router status entries to include in the document
  :param bool content: provides the str content of the descriptor rather than the class if True

  :returns: NetworkStatusDocumentV3 for the requested descriptor content
  """

  attr = {} if attr is None else dict(attr)

  # add defaults only found in a vote, consensus, or microdescriptor

  if attr.get('vote-status') == 'vote':
    extra_defaults = {
      'consensus-methods': '1 9',
      'published': '2012-09-02 22:00:00',
    }

    # votes need an authority to be valid

    if authorities is None:
      authorities = [get_directory_authority(is_vote = True)]
  else:
    extra_defaults = {
      'consensus-method': '9',
    }

  for k, v in extra_defaults.items():
    if exclude and k in exclude:
      continue  # explicitly excluding this field
    elif k not in attr:
      attr[k] = v

  desc_content = _get_descriptor_content(attr, exclude, NETWORK_STATUS_DOCUMENT_HEADER, NETWORK_STATUS_DOCUMENT_FOOTER)

  # inject the authorities and/or routers between the header and footer
  if authorities:
    if b'directory-footer' in desc_content:
      footer_div = desc_content.find(b'\ndirectory-footer') + 1
    elif b'directory-signature' in desc_content:
      footer_div = desc_content.find(b'\ndirectory-signature') + 1
    else:
      if routers:
        desc_content += b'\n'

      footer_div = len(desc_content) + 1

    authority_content = stem.util.str_tools._to_bytes('\n'.join([str(a) for a in authorities]) + '\n')
    desc_content = desc_content[:footer_div] + authority_content + desc_content[footer_div:]

  if routers:
    if b'directory-footer' in desc_content:
      footer_div = desc_content.find(b'\ndirectory-footer') + 1
    elif b'directory-signature' in desc_content:
      footer_div = desc_content.find(b'\ndirectory-signature') + 1
    else:
      if routers:
        desc_content += b'\n'

      footer_div = len(desc_content) + 1

    router_content = stem.util.str_tools._to_bytes('\n'.join([str(r) for r in routers]) + '\n')
    desc_content = desc_content[:footer_div] + router_content + desc_content[footer_div:]

  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.NetworkStatusDocumentV3(desc_content, validate = True)
