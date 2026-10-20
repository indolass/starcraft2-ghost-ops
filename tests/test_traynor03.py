"""TRaynor03 "Zero Hour": configuration, order costs, plan merging, hooks, gating of the probe; one real build + verify of the playable profile."""
import argparse
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402


def resolved(preset='standard'):
    adapter = build.load_adapter('traynor03')
    cfg, name = build.resolve_config(adapter, preset)
    return adapter, cfg


class ZeroHourConfig(unittest.TestCase):
    def test_playable_profile_validates_and_has_no_probe(self):
        adapter, cfg = resolved()
        self.assertEqual(build.validate_config(cfg), [])
        self.assertNotIn('ce0', cfg)
        a = build.apply_ce0(adapter, cfg)
        text = build.build_block(a, cfg)
        self.assertNotIn('Ce0', text)
        self.assertIn('GhostOps_ZH_Gate', ''.join(h['call'] for h in build.hook_list(a)))
        self.assertTrue(text.isascii())

    def test_recommended_order_cost_is_the_documented_experimental_number(self):
        adapter, cfg = resolved()
        z = cfg['zerohour']
        self.assertEqual(z['recommended'], {'marines': 16, 'bunkers': 4, 'turrets': 4, 'scvs': 8})
        self.assertEqual(build.zerohour_cost(cfg, z['recommended']), {'minerals': 1640, 'gas': 0})
        # nothing of the 1000 / 500 of THanson01 is charged here: only the chosen order has a price
        self.assertEqual(build.zerohour_cost(cfg, {'marines': 0, 'bunkers': 0, 'turrets': 0, 'scvs': 0}), {'minerals': 0, 'gas': 0})

    def test_tactical_rules_of_this_mission(self):
        adapter, cfg = resolved()
        t = cfg['tactical']
        self.assertEqual((t['nuke']['count'], t['nuke']['both_may_aim'], t['spotter_defeat']), (2, True, False))
        self.assertEqual(t['garrison']['damage_multiplier'], 8)
        self.assertEqual(cfg['ghost_tuning']['ghost_life'], 45)
        gen = build.gen_tactical(cfg)
        self.assertIn('go_tacNukeCount = 2;', gen)
        self.assertIn('go_tacSpotterDefeat = false;', gen)
        # TRaynor02 keeps its single missile and the Spotter rule
        a2 = build.load_adapter('traynor02')
        c2, _ = build.resolve_config(a2, 'tactical')
        g2 = build.gen_tactical(c2)
        self.assertIn('go_tacNukeCount = 1;', g2)
        self.assertIn('go_tacSpotterDefeat = true;', g2)

    def test_validator_refuses_bad_orders_prices_targets_and_unknown_keys(self):
        adapter, cfg = resolved()
        for mutate in (lambda z: z['order'].update(marines=99), lambda z: z['prices']['bunkers'].update(minerals=-1), lambda z: z.update(targets=[1, 1]),
                       lambda z: z.update(surprise=1), lambda z: z.update(arrival_minutes=25), lambda z: z['texts'].pop('RaynorText'),
                       lambda z: z['order'].update(tanks=1), lambda z: z['post_arrival'].update(interval=1)):
            bad = copy.deepcopy(cfg)
            mutate(bad['zerohour'])
            self.assertTrue(build.validate_config(bad), mutate)

    def test_plan_changes_only_the_order_and_names_the_unique_file(self):
        tmp = tempfile.mkdtemp()
        plan = os.path.join(tmp, 'p.json')
        json.dump({'operation_id': 'OP0007', 'mission': 'traynor03', 'preset': 'standard', 'order': {'marines': 5, 'bunkers': 1, 'turrets': 2, 'scvs': 0}}, open(plan, 'w'))
        args = argparse.Namespace(mission='traynor03', preset='standard', source=None, multiplier=None, diag=False, plan=plan)
        adapter, cfg, name = build.context(args)
        base_adapter, base_cfg = resolved()
        self.assertEqual(cfg['zerohour']['order'], {'marines': 5, 'bunkers': 1, 'turrets': 2, 'scvs': 0})
        self.assertEqual(cfg['campaign']['operation_id'], 'OP0007')
        self.assertEqual(cfg['zerohour']['prices'], base_cfg['zerohour']['prices'])  # a plan can never change a price or a limit
        self.assertEqual(cfg['zerohour']['limits'], base_cfg['zerohour']['limits'])
        self.assertTrue(build.output_name(adapter, name).endswith('standard__OP0007.SC2Map'))
        self.assertNotEqual(build.key_for(adapter, name), build.key_for(base_adapter, name))
        bad = os.path.join(tmp, 'bad.json')
        json.dump({'operation_id': 'OP0007', 'cheat': 1}, open(bad, 'w'))
        with self.assertRaises(build.ConfigError):
            build.load_plan(bad)

    def test_data_hash_follows_the_order(self):
        adapter, cfg = resolved()
        other = copy.deepcopy(cfg)
        other['zerohour']['order']['marines'] = 7
        self.assertNotEqual(build.data_hash(cfg), build.data_hash(other))


class ZeroHourBuild(unittest.TestCase):
    def test_build_and_verify_of_the_playable_profile(self):
        src = os.path.join(build.ROOT, 'tmp', 'source', 'TRaynor03.SC2Map')
        if not os.path.isfile(src):
            self.skipTest('original map not extracted (docs/EXTRACT_MAP.md)')
        args = argparse.Namespace(mission='traynor03', preset='standard', source=None, multiplier=None, diag=False, print_only=False, start=False, plan=None)
        self.assertEqual(build.cmd_build(args), 0)


if __name__ == '__main__':
    unittest.main()
