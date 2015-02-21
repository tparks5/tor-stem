"""
Integration tests for stem.descriptor.networkstatus.
"""

import os
import unittest

import stem
import stem.descriptor
import stem.descriptor.networkstatus
import stem.version
import test.runner

from test.runner import only_run_once


class TestNetworkStatus(unittest.TestCase):
  @only_run_once
  def test_cached_consensus(self):
    """
    Parses the cached-consensus file in our data directory.
    """

    consensus_path = test.runner.get_runner().get_test_dir('cached-consensus')

    if not os.path.exists(consensus_path):
      test.runner.skip(self, '(no cached-consensus)')
      return
    elif stem.util.system.is_windows():
      # Unable to check memory usage on windows, so can't prevent hanging the
      # system if things go bad.

      test.runner.skip(self, '(unavailable on windows)')
      return

    count = 0
    with open(consensus_path, 'rb') as descriptor_file:
      for router in stem.descriptor.parse_file(descriptor_file, 'network-status-consensus-3 1.0', validate = True):
        count += 1

        # check if there's any unknown flags
        # TODO: this should be a 'new capability' check later rather than
        # failing the tests
        for flag in router.flags:
          if flag not in stem.Flag:
            raise ValueError('Unrecognized flag type: %s, found on relay %s (%s)' % (flag, router.fingerprint, router.nickname))

        unrecognized_lines = router.get_unrecognized_lines()

        if unrecognized_lines:
          self.fail('Unrecognized descriptor content: %s' % unrecognized_lines)

    # Sanity test that there's at least a hundred relays. If that's not the
    # case then this probably isn't a real, complete tor consensus.

    self.assertTrue(count > 100)

  @only_run_once
  def test_cached_microdesc_consensus(self):
    """
    Parses the cached-microdesc-consensus file in our data directory.
    """

    consensus_path = test.runner.get_runner().get_test_dir('cached-microdesc-consensus')

    if not os.path.exists(consensus_path):
      test.runner.skip(self, '(no cached-microdesc-consensus)')
      return
    elif stem.util.system.is_windows():
      test.runner.skip(self, '(unavailable on windows)')
      return

    count = 0
    with open(consensus_path, 'rb') as descriptor_file:
      for router in stem.descriptor.parse_file(descriptor_file, 'network-status-microdesc-consensus-3 1.0', validate = True):
        count += 1

        # check if there's any unknown flags
        # TODO: this should be a 'new capability' check later rather than
        # failing the tests
        for flag in router.flags:
          if flag not in stem.Flag:
            raise ValueError('Unrecognized flag type: %s, found on microdescriptor relay %s (%s)' % (flag, router.fingerprint, router.nickname))

        unrecognized_lines = router.get_unrecognized_lines()

        if unrecognized_lines:
          self.fail('Unrecognized descriptor content: %s' % unrecognized_lines)

    self.assertTrue(count > 100)
