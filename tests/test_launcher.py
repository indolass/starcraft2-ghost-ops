import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import launcher_core as lc  # noqa: E402
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeBackend:
    def __init__(self, running=False, prepare_rc=0, start_rc=0, gate=None):
        self.running, self.prepare_rc, self.start_rc, self.gate = running, prepare_rc, start_rc, gate
        self.prepared, self.started, self.configured = [], [], []

    def configure(self, game_dir):
        self.configured.append(game_dir)

    def sc2_running(self):
        return self.running

    def prepare(self, mission, preset, progress):
        self.prepared.append((mission, preset))
        progress('check')
        progress('build')
        if self.gate:
            self.gate.wait(5)
        return self.prepare_rc

    def start(self, mission, preset):
        self.started.append((mission, preset))
        return self.start_rc


def make(tmp, **kw):
    settings = lc.Settings(os.path.join(tmp, 'settings.json'))
    backend = FakeBackend(**kw)
    return lc.Launcher(settings, backend, log_fn=lambda m: None), settings, backend


class SettingsTests(unittest.TestCase):
    def test_first_run_is_traynor01_easy(self):
        with tempfile.TemporaryDirectory() as t:
            s = lc.Settings(os.path.join(t, 's.json'))
            self.assertEqual(s.mission(), 'traynor01')
            self.assertEqual(s.profile('traynor01'), 'easy')

    def test_selection_is_saved_and_restored(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 's.json')
            lc.Settings(p).remember('traynor01', 'extreme')
            again = lc.Settings(p)
            self.assertEqual((again.mission(), again.profile('traynor01')), ('traynor01', 'extreme'))

    def test_damaged_or_stale_settings_fall_back(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 's.json')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('{"mission": "nope", "profiles": {"traynor01": "gone"}')
            s = lc.Settings(p)
            self.assertEqual((s.mission(), s.profile('traynor01')), ('traynor01', 'easy'))
            with open(p, 'w', encoding='utf-8') as f:
                f.write('{"mission": "nope", "profiles": {"traynor01": "gone"}}')
            s = lc.Settings(p)
            self.assertEqual((s.mission(), s.profile('traynor01')), ('traynor01', 'easy'))

    def test_game_path_is_a_setting(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 's.json')
            s = lc.Settings(p)
            s.data['game_dir'] = r'X:\Games\SC2'
            s.save()
            self.assertEqual(lc.Settings(p).game_dir, r'X:\Games\SC2')
            self.assertIsNotNone(lc.game_dir_problem(r'X:\no\such\dir'))


class ProfilesTests(unittest.TestCase):
    def test_three_profiles_for_traynor01_none_for_prototypes(self):
        names = [p['name'] for p in lc.profiles_of('traynor01')]
        self.assertEqual(names, ['easy', 'hard', 'extreme'])
        self.assertEqual([p['name'] for p in lc.profiles_of('traynor02')], ['tactical'])  # the old prototype preset is hidden (CLI only)
        self.assertTrue(lc.profiles_of('traynor02')[0]['experimental'])
        self.assertEqual(lc.profiles_of('ttychus01'), [])

    def test_only_extreme_is_experimental(self):
        flags = {p['name']: p['experimental'] for p in lc.profiles_of('traynor01')}
        self.assertEqual(flags, {'easy': False, 'hard': False, 'extreme': True})

    def test_details_show_exact_numbers(self):
        extreme = '\n'.join(lc.detail_lines('traynor01', 'extreme'))
        self.assertIn('Призраки: 1, здоровье 45/45', extreme)
        self.assertIn('Перезарядка Snipe: 8 с', extreme)
        self.assertIn('Snipe: 0 энергии', extreme)
        self.assertNotIn('отдельно', extreme)
        self.assertIn('Призраки: 2, здоровье 100/100', '\n'.join(lc.detail_lines('traynor01', 'hard')))
        self.assertIn('5 с у каждого призрака отдельно', '\n'.join(lc.detail_lines('traynor01', 'hard')))

    def test_mission_description_does_not_promise_two_ghosts(self):
        self.assertNotIn('Два призрака', lc.mission_info('traynor01')['description'])
        self.assertIn('здоровье 100/100', '\n'.join(lc.detail_lines('traynor01', 'easy')))


class LauncherTests(unittest.TestCase):
    def test_gui_choice_reaches_existing_logic(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t)
            stages = []
            r = l.run('traynor01', 'extreme', stages.append)
            self.assertTrue(r.ok)
            self.assertEqual(b.prepared, [('traynor01', 'extreme')])
            self.assertEqual(b.started, [('traynor01', 'extreme')])
            self.assertEqual(stages, ['check', 'build', 'start'])
            self.assertEqual(s.profile('traynor01'), 'extreme')
            self.assertFalse(l.busy)

    def test_repeat_click_does_not_start_second_preparation(self):
        with tempfile.TemporaryDirectory() as t:
            gate = threading.Event()
            l, s, b = make(t, gate=gate)
            done = threading.Event()
            self.assertTrue(l.start_async('traynor01', 'hard', lambda x: None, lambda r: done.set()))
            self.assertFalse(l.start_async('traynor01', 'hard', lambda x: None, lambda r: None))
            gate.set()
            self.assertTrue(done.wait(5))
            self.assertEqual(len(b.prepared), 1)
            self.assertFalse(l.busy)

    def test_error_releases_ui_and_keeps_selection(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t, prepare_rc=2)
            r = l.run('traynor01', 'hard')
            self.assertFalse(r.ok)
            self.assertEqual(r.kind, 'error')
            self.assertFalse(l.busy)
            self.assertEqual(s.profile('traynor01'), 'hard')
            self.assertEqual(b.started, [])
            self.assertTrue(l.begin())  # can try again

    def test_unexpected_exception_releases_ui(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t)

            def boom(*a):
                raise RuntimeError('boom')
            b.prepare = boom
            r = l.run('traynor01', 'easy')
            self.assertFalse(r.ok)
            self.assertFalse(l.busy)

    def test_running_game_is_reported_not_touched(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t, running=True)
            r = l.run('traynor01', 'easy')
            self.assertEqual(r.kind, 'busy-game')
            self.assertEqual(b.prepared, [])
            self.assertEqual(b.started, [])
            self.assertFalse(l.busy)

    def test_unknown_profile_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t)
            self.assertFalse(l.run('traynor01', 'nightmare').ok)
            self.assertFalse(l.run('traynor02', 'easy').ok)
            self.assertEqual(b.prepared, [])

    def test_prototype_starts_without_profile(self):
        with tempfile.TemporaryDirectory() as t:
            l, s, b = make(t)
            self.assertTrue(l.run('ttychus01', None).ok)
            self.assertEqual(b.started, [('ttychus01', None)])


if __name__ == '__main__':
    unittest.main()


class TestGameLaunchGuard(unittest.TestCase):
    """No project tool may start a full screen test game (Owner rule): the one start function forces the windowed test form."""

    def test_windowed_command_replaces_every_display_argument(self):
        import test_launch
        cmd = '"SC2Switcher_x64.exe" -run "m.SC2Map" -difficulty 3 -displaymode 2'
        out = test_launch.windowed_command(cmd, 10, 20, 1024, 768)
        self.assertEqual(out.count('-displaymode'), 1)
        self.assertIn('-displaymode 0 -windowwidth 1024 -windowheight 768 -windowx 10 -windowy 20', out)
        again = test_launch.windowed_command(out, 5, 6, 800, 600)
        self.assertEqual(again.count('-windowwidth'), 1)
        self.assertIn('-windowx 5 -windowy 6', again)
        self.assertNotIn('-displaymode 2', again)

    def test_only_owner_calls_may_skip_the_guard(self):
        import build
        src = open(os.path.join(ROOT, 'tools', 'build.py'), encoding='utf-8').read()
        self.assertEqual(src.count('_raw_start('), 2)  # the definition and the owner branch of start_detached
        for f in ('launcher_core.py', 'campaign_flow.py'):
            self.assertIn('start_detached(command, owner=True)', open(os.path.join(ROOT, 'tools', f), encoding='utf-8').read())
        for f in ('test_launch.py', 'ce0_session.py', 'ce0_campaign_e2e.py', 'save_lock_probe.py'):
            self.assertNotIn('owner=True', open(os.path.join(ROOT, 'tools', f), encoding='utf-8').read())
