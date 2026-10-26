"""Own-test-game bookkeeping: a record without a creation time is never made, a foreign pid is never closed."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import isolation  # noqa: E402


class OwnedCleanup(unittest.TestCase):
    def test_process_created_of_a_non_sc2_pid_is_none(self):
        self.assertIsNone(isolation.process_created(os.getpid()))
        self.assertIsNone(isolation.process_created(999999999))

    def test_a_foreign_pid_is_not_owned_and_not_closed(self):
        self.assertFalse(isolation.is_owned(os.getpid()))
        self.assertFalse(isolation.close_owned(os.getpid()))

    def test_no_record_is_written_without_a_creation_time(self):
        old = isolation.OWNED
        try:
            isolation.OWNED = os.path.join(ROOT, 'tmp', 'owned_test_unused.json')
            real, isolation.process_created = isolation.process_created, lambda pid: None
            try:
                orig_sleep, isolation.time.sleep = isolation.time.sleep, lambda s: None
                self.assertIsNone(isolation.record_owned(4242, 'x'))
            finally:
                isolation.process_created = real
                isolation.time.sleep = orig_sleep
            self.assertFalse(os.path.exists(isolation.OWNED))
        finally:
            isolation.OWNED = old


if __name__ == '__main__':
    unittest.main()
