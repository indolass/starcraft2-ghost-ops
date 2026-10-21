"""CE-0: the technical probe (key "ce0") exists only in hidden *_dev presets and never reaches a playable build."""
import copy
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402


def block(mission, preset):
    adapter = build.load_adapter(mission)
    cfg, name = build.resolve_config(adapter, preset)
    return build.build_block(build.apply_ce0(adapter, cfg), cfg), cfg, build.apply_ce0(adapter, cfg)


class Ce0Gating(unittest.TestCase):
    PLAYABLE = [('traynor02', 'tactical'), ('traynor02', 'prototype'), ('thanson01', 'sniper'), ('traynor01', 'easy'), ('traynor01', 'hard'),
                ('traynor01', 'extreme'), ('ttychus01', None)]

    def test_no_playable_profile_contains_the_probe(self):
        for mission, preset in self.PLAYABLE:
            text, cfg, adapter = block(mission, preset)
            self.assertNotIn('ce0', cfg, (mission, preset))
            self.assertNotIn('Ce0', text, (mission, preset))
            self.assertNotIn('go_c0', text, (mission, preset))
            self.assertFalse(adapter.get('ce0'), (mission, preset))
            self.assertFalse([h for h in build.hook_list(adapter) if 'Ce0' in h['call']], (mission, preset))

    def test_dev_presets_contain_the_probe_and_its_hooks(self):
        for mission, preset in (('traynor02', 'ce0_dev'), ('traynor02', 'ce0_wait_dev'), ('thanson01', 'ce0_dev')):
            text, cfg, adapter = block(mission, preset)
            self.assertIn('GhostOps_Ce0_Start', text)
            self.assertIn('go_c0Enabled = true;', text)
            self.assertTrue([h for h in build.hook_list(adapter) if 'GhostOps_Ce0_Start' in h['call']], (mission, preset))
            self.assertEqual(build.validate_config(cfg), [], (mission, preset))
            self.assertTrue(text.isascii())

    def test_the_probe_is_refused_outside_a_dev_profile(self):
        adapter = build.load_adapter('traynor02')
        cfg, _ = build.resolve_config(adapter, 'ce0_dev')
        bad = copy.deepcopy(cfg)
        bad['profile']['name'] = 'tactical'
        self.assertTrue([e for e in build.validate_config(bad) if 'development only' in e])
        bad = copy.deepcopy(cfg)
        bad['ce0']['surprise'] = 1
        self.assertTrue([e for e in build.validate_config(bad) if 'not supported' in e])

    def test_the_data_hash_changes_with_the_settings_and_not_with_the_profile_label(self):
        adapter = build.load_adapter('traynor02')
        cfg, _ = build.resolve_config(adapter, 'ce0_dev')
        a = build.gen_ce0(cfg)
        cfg2 = copy.deepcopy(cfg)
        cfg2['profile']['label'] = 'other label'
        self.assertEqual(a, build.gen_ce0(cfg2))
        cfg3 = copy.deepcopy(cfg)
        cfg3['tactical']['story']['second_delay'] = 99
        self.assertNotEqual(a, build.gen_ce0(cfg3))


if __name__ == '__main__':
    unittest.main()
