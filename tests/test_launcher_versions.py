"""The launcher screen shows ONE current version per mission and a closed archive: data side (no window, no game). The real window is checked by tools/launcher_window_check.py."""
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import launcher_core as lc  # noqa: E402
import build  # noqa: E402

MISSIONS = [m['id'] for m in lc.MISSIONS]


class FakeBackend:
    def __init__(self):
        self.started = []

    def configure(self, g):
        pass

    def sc2_running(self):
        return False

    def prepare(self, m, p, progress):
        progress('check')
        return 0

    def start(self, m, p):
        self.started.append((m, p))
        return 0

    def build_hash(self, m, p):
        return 'h123'


class CurrentVersion(unittest.TestCase):
    def test_every_mission_names_its_current_version_explicitly(self):
        for m in MISSIONS:
            raw = build.load_json(build.load_adapter(m)['config'])
            n = raw['launcher']['current_revision']
            self.assertIsInstance(n, int, m)
            self.assertEqual(lc.current_revision(m), n)
            cur = [r for r in lc.revisions_of(m) if r['current']]
            self.assertEqual([r['number'] for r in cur], [n], m)

    def test_missing_or_wrong_current_is_an_error_never_a_guess(self):
        real = build.load_json

        def fake(rel):
            d = real(rel)
            if rel.startswith('config/thanson02'):
                d = json.loads(json.dumps(d))
                d['launcher'] = {'current_revision': 99}
            return d
        with mock.patch.object(build, 'load_json', fake):
            with self.assertRaises(lc.LauncherDataError):
                lc.current_revision('thanson02')

    def test_current_versions_of_today(self):
        self.assertEqual({m: lc.current_revision(m) for m in MISSIONS},
                         {'traynor01': 1, 'traynor02': 2, 'thanson01': 6, 'thanson02': 6, 'traynor03': 6, 'ttychus01': 1})

    def test_free_test_and_campaign_profiles_of_one_revision_are_one_version(self):
        r6 = lc.revision_by_number('traynor03', 6)
        self.assertEqual(r6['modes'], ['free', 'campaign'])
        self.assertEqual(lc.preset_for(r6, 'free'), 'defence_r6_free')
        self.assertIsNone(lc.preset_for(r6, 'campaign'))  # the campaign mode opens the campaign window, no map is started from here
        self.assertEqual(len([r for r in lc.revisions_of('traynor03') if r['number'] == 6]), 1)

    def test_difficulty_is_a_real_choice_inside_a_version(self):
        r = lc.revision_by_number('traynor01', 1)
        self.assertEqual(lc.difficulties_of(r, 'standalone'), ['Лёгкий', 'Сложный', 'Экстремальный'])
        self.assertEqual([lc.preset_for(r, 'standalone', d) for d in lc.difficulties_of(r, 'standalone')], ['easy', 'hard', 'extreme'])
        self.assertEqual(lc.difficulties_of(lc.revision_by_number('traynor03', 6), 'free'), [])

    def test_archive_has_no_current_no_hidden_profile_and_keeps_every_old_version(self):
        arch = lc.archive_of('traynor03')
        self.assertEqual([r['number'] for r in arch], [5, 4, 3, 2, 1, 0])
        listed = {p for r in lc.revisions_of('traynor03') for p in r['presets']}
        raw = build.load_json(build.load_adapter('traynor03')['config'])
        self.assertTrue(all(not raw['presets'][p].get('hidden') for p in listed))
        self.assertTrue({'standard', 'defence', 'defence_next', 'defence_r3', 'defence_r5_free'} <= listed)  # nothing is deleted for the sake of a tidy screen

    def test_revisions_are_sorted_as_numbers(self):
        real = build.load_json

        def fake(rel):
            d = real(rel)
            if rel.startswith('config/thanson02'):
                d = json.loads(json.dumps(d))
                base = d['presets']['epidemic_free_r6']
                for n in (9, 10, 11):
                    p = json.loads(json.dumps(base))
                    p['launch']['revision'] = n
                    d['presets']['x%d' % n] = p
                d['launcher']['current_revision'] = 11
            return d
        with mock.patch.object(build, 'load_json', fake):
            nums = [r['number'] for r in lc.revisions_of('thanson02')]
            self.assertEqual(nums[:3], [11, 10, 9])  # not '9' > '10' as text
            self.assertEqual(nums, sorted(nums, reverse=True))

    def test_every_visible_profile_has_launch_data_and_at_most_three_changes(self):
        for m in MISSIONS:
            raw = build.load_json(build.load_adapter(m)['config'])
            for name, p in raw['presets'].items():
                if p.get('hidden'):
                    continue
                self.assertIn('launch', p, (m, name))
                self.assertTrue(1 <= len(p['launch']['changes']) <= 3, (m, name))
        for m in MISSIONS:
            for r in lc.revisions_of(m):
                self.assertLessEqual(len(r['changes']), 3)

    def test_the_launcher_block_is_not_part_of_the_build(self):
        ad = build.load_adapter('thanson02')
        self.assertNotIn('launcher', build.resolve_config(ad, 'epidemic_free_r6')[0])

    def test_composition_matches_the_selected_profile(self):
        self.assertIn('призраки 2', lc.composition_line('traynor03', 'defence_r6_free'))
        self.assertIn('мародёры 3', lc.composition_line('ttychus01', 'grab_free'))
        self.assertIn('призрак', lc.composition_line('traynor01', 'extreme'))
        self.assertNotEqual(lc.composition_line('traynor01', 'hard'), lc.composition_line('traynor01', 'extreme'))


class OperationsAndRecords(unittest.TestCase):
    def test_an_open_operation_shows_its_own_version(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'campaign.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'version': 1, 'stock': {}, 'ledger': [], 'accepted_results': [], 'launch': None, 'operations': {
                    'OP1': {'mission': 'traynor03', 'profile': 'defence_r5', 'state': 'paid'}, 'OP2': {'mission': 'traynor03', 'profile': 'defence_r3', 'state': 'accepted'},
                    'OP3': {'mission': 'thanson01', 'profile': 'sniper_next_r5', 'state': 'started'}}}, f)
            ops = lc.open_operations('traynor03', p)
            self.assertEqual([(o['id'], o['revision']) for o in ops], [('OP1', 5)])  # the accepted one is finished; another mission's operation is not shown
            self.assertEqual(lc.open_operations('traynor03', os.path.join(t, 'none.json')), [])

    def test_the_record_of_the_last_launch_says_what_really_ran(self):
        with tempfile.TemporaryDirectory() as t:
            s = lc.Settings(os.path.join(t, 's.json'))
            b = FakeBackend()
            launcher = lc.Launcher(s, b, log_fn=lambda m: None)
            self.assertTrue(launcher.begin())
            info = {'mission': 'traynor03', 'revision': 4, 'revision_label': 'Версия 4', 'archive': True, 'mode': 'free', 'difficulty': None}
            r = launcher.run('traynor03', 'defence_r4_free', lambda st: None, info)
            self.assertTrue(r.ok)
            rec = lc.Settings(os.path.join(t, 's.json')).data['last_launch']  # saved to the file, readable by the next session
            self.assertEqual((rec['preset'], rec['revision'], rec['archive'], rec['build_hash']), ('defence_r4_free', 4, True, 'h123'))
            self.assertTrue(rec['map'].endswith('GhostOps_TRaynor03_defence_r4_free.SC2Map'))
            text = lc.last_launch_text(rec)
            self.assertIn('Версия 4', text)
            self.assertIn('(архив)', text)
            self.assertIn('defence_r4_free', text)

    def test_a_failed_preparation_is_remembered_for_that_profile_only(self):
        with tempfile.TemporaryDirectory() as t:
            s = lc.Settings(os.path.join(t, 's.json'))
            b = FakeBackend()
            b.prepare = lambda m, p, progress: 3
            launcher = lc.Launcher(s, b, log_fn=lambda m: None)
            launcher.begin()
            r = launcher.run('thanson02', 'epidemic_free_r6', lambda st: None)
            self.assertFalse(r.ok)
            self.assertIn('Не удалось подготовить', s.last_error_for('thanson02', 'epidemic_free_r6'))
            self.assertIsNone(s.last_error_for('thanson02', 'epidemic_free_r5'))
            self.assertIn('Ошибка подготовки', lc.build_state_text(None, s.last_error_for('thanson02', 'epidemic_free_r6')))

    def test_test_info_names_version_mode_profile_map(self):
        text = lc.test_info('thanson02', 6, 'free', 'epidemic_free_r6', None, r'E:\Games\StarCraft II', False, 'abc')
        for part in ('Эпидемия', 'Версия 6 (текущая для проверки)', 'Свободный тест', 'epidemic_free_r6', 'GhostOps_THanson02_epidemic_free_r6.SC2Map', 'Сборка: abc'):
            self.assertIn(part, text)
        arch = lc.test_info('thanson02', 4, 'free', 'epidemic_free_r4', None)
        self.assertIn('(архив)', arch)

    def test_build_states_are_told_apart(self):
        self.assertEqual(lc.build_state_text('ready'), 'Сборка установлена')
        self.assertIn('Нужно собрать', lc.build_state_text('needs_build'))
        self.assertIn('Нужно обновить установку', lc.build_state_text('needs_install'))
        self.assertIn('Ошибка подготовки: нет места', lc.build_state_text('ready', 'нет места'))

    def test_the_queue_panel_drops_old_finished_jobs(self):
        old = '2020-01-01 00:00:00'
        st = {'jobs': [{'id': 'T1', 'label': 'x', 'state': 'done', 'mission': 'm', 'preset': 'p', 'log': 'l', 'updated': old}, {'id': 'T2', 'label': 'y', 'state': 'cancelled', 'mission': 'm', 'preset': 'p', 'updated': old},
                       {'id': 'T3', 'label': 'z', 'state': 'error', 'mission': 'm', 'preset': 'p', 'updated': old}], 'runner_alive': True}
        self.assertIsNone(lc.queue_summary(st))
        st['jobs'].append({'id': 'T4', 'label': 'w', 'state': 'running', 'mission': 'm', 'preset': 'p', 'phase': 'run', 'updated': old})
        self.assertEqual(lc.queue_summary(st)['job'], 'T4')


if __name__ == '__main__':
    unittest.main()
