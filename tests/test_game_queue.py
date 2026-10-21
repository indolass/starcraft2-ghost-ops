"""Test queue (tools/test_queue.py) and isolation guards (tools/isolation.py) on substitute processes: no game is ever started here."""
import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import isolation  # noqa: E402
import test_queue as tq  # noqa: E402


class Fake:
    """Fake clock and fake StarCraft II process list; `pids_at` maps a clock value to the pids present."""

    def __init__(self):
        self.t = 1000.0
        self.pids_at = lambda t: []
        self.sleeps = []
        self.hook = None

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s
        if self.hook:
            self.hook(self)

    def pids(self):
        return list(self.pids_at(self.t))


class QueueBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = {k: getattr(tq, k) for k in ('QDIR', 'QFILE', 'LOCK', 'STOP', 'BEAT', 'sc2_pids', 'now', 'sleep', 'prepare_build', 'cleanup_build')}
        tq.QDIR = self.tmp
        tq.QFILE = os.path.join(self.tmp, 'queue.json')
        tq.LOCK = os.path.join(self.tmp, 'runner.lock')
        tq.STOP = os.path.join(self.tmp, 'STOP')
        tq.BEAT = os.path.join(self.tmp, 'runner.json')
        self.fake = Fake()
        tq.sc2_pids, tq.now, tq.sleep = self.fake.pids, self.fake.now, self.fake.sleep
        self.prepared = []
        tq.prepare_build = lambda job: self.prepared.append(job['id']) or 0
        tq.cleanup_build = lambda job: None
        self.marker = os.path.join(self.tmp, 'marker.txt')

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tq, k, v)

    def job(self, code="pass", timeout=10**6):
        script = ("import os,sys; open(r'%s','a').write(os.environ.get('GHOSTOPS_QUEUE_JOB','')+'|'+os.environ.get('GHOSTOPS_CAMPAIGN_FILE','')+'|'"
                  "+os.environ.get('GHOSTOPS_BANK_DIR','')+chr(10)); %s" % (self.marker, code))
        return tq.enqueue('t', 'traynor03', 'defence_next_dev', [sys.executable, '-c', script], timeout)

    def starts(self):
        return open(self.marker).read().splitlines() if os.path.exists(self.marker) else []


class Waiting(QueueBase):
    def test_busy_game_keeps_the_job_waiting_and_nothing_is_started(self):
        j = self.job()
        self.fake.pids_at = lambda t: [4242]
        polls = []

        def hook(f):
            polls.append(f.t)
            if len(polls) == 6:
                tq.request_cancel(j['id'])
        self.fake.hook = hook
        r = tq.Runner()
        self.assertTrue(r.acquire())
        self.assertFalse(r.wait_for_game(tq.get_job(j['id'])))
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.prepared, [])
        self.assertTrue(all(abs(s - tq.POLL_BUSY) < 0.01 for s in self.fake.sleeps))  # checked about every 5 s
        self.assertEqual(tq.get_job(j['id'])['state'], 'cancelled')
        r.lock.close()

    def test_exactly_one_test_starts_after_the_game_closed_and_the_settle_time(self):
        j = self.job()
        self.fake.pids_at = lambda t: [4242] if t < 1020 else []
        self.assertEqual(tq.Runner(idle_exit=3).loop(), 0)
        self.assertEqual(len(self.starts()), 1)
        self.assertEqual(self.prepared, [j['id']])
        self.assertEqual(tq.get_job(j['id'])['state'], 'done')
        self.assertGreaterEqual(self.fake.t, 1020 + tq.SETTLE)  # the launch came at least 10 s after the game disappeared

    def test_a_game_restarted_during_the_wait_postpones_the_test(self):
        j = self.job()
        self.fake.pids_at = lambda t: [7] if (t < 1010 or 1016 <= t < 1030) else []
        tq.Runner(idle_exit=3).loop()
        self.assertEqual(len(self.starts()), 1)
        self.assertGreaterEqual(self.fake.t, 1030 + tq.SETTLE)
        self.assertEqual(tq.get_job(j['id'])['state'], 'done')

    def test_cancel_before_the_free_game_never_starts_anything(self):
        j = self.job()
        self.assertEqual(tq.request_cancel(j['id']), [j['id']])
        tq.Runner(idle_exit=2).loop()
        self.assertEqual(self.starts(), [])
        self.assertEqual(self.prepared, [])
        self.assertEqual(tq.get_job(j['id'])['state'], 'cancelled')

    def test_stop_flag_starts_no_next_job(self):
        self.job()
        open(tq.STOP, 'w').close()
        tq.Runner(idle_exit=2).loop()
        self.assertEqual(self.starts(), [])
        self.assertEqual(tq.status()['jobs'][0]['state'], 'waiting')


class Safety(QueueBase):
    def test_two_runners_cannot_both_run(self):
        a, b = tq.Runner(), tq.Runner()
        self.assertTrue(a.acquire())
        self.assertFalse(b.acquire())
        self.assertTrue(tq.runner_alive())
        a.lock.close()

    def test_a_job_has_its_own_data_directory(self):
        j = self.job()
        tq.Runner(idle_exit=2).loop()
        _, campaign, bank = self.starts()[0].split('|')
        self.assertTrue(campaign.startswith(self.tmp) and bank.startswith(self.tmp))
        self.assertIn(j['id'], campaign)
        self.assertFalse(campaign.lower().startswith(os.path.join(os.environ.get('APPDATA', 'x'), 'GhostOps').lower()))

    def test_conflict_exit_9_returns_to_waiting_and_is_bounded(self):
        j = self.job(code='sys.exit(9)')
        tq.Runner(idle_exit=2).loop()
        got = tq.get_job(j['id'])
        self.assertEqual(got['state'], 'error')  # given up after MAX_CONFLICTS, never endless
        self.assertEqual(got['conflicts'], tq.MAX_CONFLICTS)
        self.assertEqual(len(self.starts()), tq.MAX_CONFLICTS)

    def test_cancel_of_a_running_job_stops_it(self):
        j = self.job(code='import time; time.sleep(120)')
        state = {'n': 0}

        def hook(f):
            if tq.get_job(j['id'])['state'] == 'running':
                state['n'] += 1
                if state['n'] == 3:
                    tq.request_cancel(j['id'])
        self.fake.hook = hook
        tq.Runner(idle_exit=2).loop()
        self.assertEqual(tq.get_job(j['id'])['state'], 'cancelled')

    def test_interrupted_job_is_shown_and_never_started_automatically(self):
        j = self.job()
        tq.update_job(j['id'], state='running')
        st = tq.status()
        self.assertEqual(st['jobs'][0]['state'], 'interrupted')
        tq.Runner(idle_exit=2).loop()
        self.assertEqual(self.starts(), [])
        self.assertTrue(tq.resume(j['id']))
        self.assertEqual(tq.get_job(j['id'])['state'], 'waiting')

    def test_a_finished_job_is_not_changed_by_a_late_writer(self):
        j = self.job()
        tq.request_cancel(j['id'])
        tq.update_job(j['id'], state='running')
        self.assertEqual(tq.get_job(j['id'])['state'], 'cancelled')


class Isolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (isolation.REGISTRY, isolation.FROZEN, isolation.MAPS_DIR, isolation.OWNED, isolation.running_commands)
        isolation.REGISTRY = os.path.join(self.tmp, 'owner_maps.json')
        isolation.FROZEN = os.path.join(self.tmp, 'frozen')
        isolation.MAPS_DIR = os.path.join(self.tmp, 'maps')
        isolation.OWNED = os.path.join(self.tmp, 'owned.json')
        os.makedirs(isolation.MAPS_DIR)
        self.cmds = []
        isolation.running_commands = lambda: list(self.cmds)

    def tearDown(self):
        isolation.REGISTRY, isolation.FROZEN, isolation.MAPS_DIR, isolation.OWNED, isolation.running_commands = self.saved

    def test_protected_map_is_never_changed_and_a_dev_map_is(self):
        owner = os.path.join(isolation.MAPS_DIR, 'GhostOps_X_defence.SC2Map')
        open(owner, 'wb').write(b'owner')
        self.assertEqual(isolation.protect(owner), 'new')
        self.assertEqual(isolation.protect(owner), 'same')
        open(owner, 'wb').write(b'changed')
        self.assertEqual(isolation.protect(owner), 'changed')  # never silently re-registered
        with self.assertRaises(isolation.Protected):
            isolation.check_change(owner, 'removed')
        isolation.check_change(os.path.join(isolation.MAPS_DIR, 'GhostOps_X_defence_next_dev.SC2Map'))  # its own name: allowed

    def test_the_map_of_a_running_game_is_protected_even_when_not_registered(self):
        m = os.path.join(isolation.MAPS_DIR, 'GhostOps_Y.SC2Map')
        self.cmds = [(10, '2026-10-21T10:00:00', '"E:\\SC2_x64.exe" -run "%s" -displaymode 0' % m)]
        with self.assertRaises(isolation.Protected):
            isolation.check_change(m, 'overwritten')

    def test_ownership_needs_pid_and_creation_time(self):
        self.cmds = [(55, '2026-10-21T10:00:00', 'x')]
        isolation.record_owned(55, 'test')
        self.assertTrue(isolation.is_owned(55))
        self.cmds = [(55, '2026-10-21T11:30:00', 'x')]  # the pid was reused by another process
        self.assertFalse(isolation.is_owned(55))
        self.assertFalse(isolation.close_owned(55))

    def test_build_guard_refuses_uninstall_of_a_protected_install(self):
        import build
        owner = os.path.join(isolation.MAPS_DIR, 'GhostOps_Z.SC2Map')
        open(owner, 'wb').write(b'owner')
        isolation.protect(owner)
        old = build.install_manifest_path
        build.install_manifest_path = lambda key: os.path.join(self.tmp, 'install_%s.json' % key)
        try:
            json.dump({'file': owner, 'sha256': build.sha256(b'owner'), 'created_dir': False, 'dir': isolation.MAPS_DIR}, open(build.install_manifest_path('k'), 'w'))
            self.assertEqual(build.uninstall_key('k', 'k'), 6)
            self.assertTrue(os.path.exists(owner))
        finally:
            build.install_manifest_path = old


class LauncherSummary(unittest.TestCase):
    def job(self, state, **kw):
        j = {'id': 'T0001', 'label': 'salvo', 'mission': 'traynor03', 'preset': 'defence_next_dev', 'state': state, 'phase': 'p', 'result': 'r', 'log': 'L'}
        j.update(kw)
        return j

    def test_nothing_to_show(self):
        import launcher_core as core
        self.assertIsNone(core.queue_summary({'jobs': [], 'runner_alive': False}))

    def test_waiting_shows_mission_build_stage_and_cancel(self):
        import launcher_core as core
        sm = core.queue_summary({'jobs': [self.job('waiting')], 'runner_alive': True})
        self.assertIn('traynor03 / defence_next_dev', sm['text'])
        self.assertIn('ожидает', sm['text'])
        self.assertIn('cancel', sm['actions'])
        self.assertNotIn('resume', sm['actions'])

    def test_interrupted_offers_resume_and_cancel_and_finished_shows_log(self):
        import launcher_core as core
        sm = core.queue_summary({'jobs': [self.job('interrupted')], 'runner_alive': False})
        self.assertEqual(sorted(sm['actions']), ['cancel', 'open_log', 'resume'])
        sm = core.queue_summary({'jobs': [self.job('done')], 'runner_alive': False})
        self.assertIn('Журнал: L', sm['text'])
        self.assertNotIn('cancel', sm['actions'])


if __name__ == '__main__':
    unittest.main()
