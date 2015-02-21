"""
Integration tests for stem.descriptor.extrainfo_descriptor.
"""

import os
import unittest

import stem.descriptor
import test.runner

from test.runner import only_run_once


class TestExtraInfoDescriptor(unittest.TestCase):
  @only_run_once
  def test_cached_descriptor(self):
    """
    Parses the cached descriptor file in our data directory, checking that it
    doesn't raise any validation issues and looking for unrecognized descriptor
    additions.
    """

    descriptor_path = test.runner.get_runner().get_test_dir('cached-extrainfo')

    if not os.path.exists(descriptor_path):
      test.runner.skip(self, '(no cached descriptors)')
      return

    with open(descriptor_path, 'rb') as descriptor_file:
      for desc in stem.descriptor.parse_file(descriptor_file, 'extra-info 1.0', validate = True):
        unrecognized_lines = desc.get_unrecognized_lines()

        if desc.dir_v2_responses_unknown:
          self.fail('Unrecognized statuses on dirreq-v2-resp lines: %s' % desc.dir_v2_responses_unknown)
        elif desc.dir_v3_responses_unknown:
          self.fail('Unrecognized statuses on dirreq-v3-resp lines: %s' % desc.dir_v3_responses_unknown)
        elif desc.dir_v2_direct_dl_unknown:
          self.fail('Unrecognized stats on dirreq-v2-direct-dl lines: %s' % desc.dir_v2_direct_dl_unknown)
        elif desc.dir_v3_direct_dl_unknown:
          self.fail('Unrecognized stats on dirreq-v3-direct-dl lines: %s' % desc.dir_v2_direct_dl_unknown)
        elif desc.dir_v2_tunneled_dl_unknown:
          self.fail('Unrecognized stats on dirreq-v2-tunneled-dl lines: %s' % desc.dir_v2_tunneled_dl_unknown)
        elif unrecognized_lines:
          # TODO: This isn't actually a problem, and rather than failing we
          # should alert the user about these entries at the end of the tests
          # (along with new events, getinfo options, and such). For now though
          # there doesn't seem to be anything in practice to trigger this so
          # failing to get our attention if it does.

          self.fail('Unrecognized descriptor content: %s' % unrecognized_lines)
