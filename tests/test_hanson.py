import argparse
import copy
import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402
import launcher_core  # noqa: E402
import sc2mpq  # noqa: E402

ADAPTER = build.load_adapter('thanson01')
SRC = os.path.join(ROOT, 'tmp', 'source', 'THanson01.SC2Map')


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class HansonConfig(unittest.TestCase):
    def setUp(self):
        self.cfg, self.name = build.resolve_config(ADAPTER, 'sniper')

    def test_config_valid_and_numbers(self):
        self.assertEqual(self.name, 'sniper')
        self.assertEqual(build.validate_config(self.cfg), [])
        gt = self.cfg['ghost_tuning']
        self.assertEqual(self.cfg['operatives']['squad'], ['Ghost'])  # exactly one ordinary Ghost
        self.assertEqual(gt['ghost_life'], 45)
        self.assertEqual(gt['snipe'], {'cost': 0, 'damage': 1000, 'cast_time': 0.3, 'cooldown': 1.0, 'exclude_friendly': True})
        self.assertEqual(gt['remove_abilities'], ['TacNukeStrike', 'EMP'])
        self.assertTrue(self.cfg['operatives']['ghost_permanent_cloak'])
        self.assertTrue(self.cfg['operatives']['ghost_start_cloaked'])
        self.assertFalse(self.cfg['operatives']['start_hold_fire'])  # the ordinary rifle keeps working
        self.assertEqual(self.cfg['difficulty']['expected'], 3)  # Hard
        self.assertEqual(self.cfg['base_support']['damage_multiplier'], 1)  # no balance rules of the other missions
        self.assertNotIn('tactical', self.cfg)
        self.assertNotIn('scene', self.cfg)
        self.assertNotIn('audio', self.cfg)
        self.assertTrue(self.cfg['hanson']['lock_development'])
        self.assertTrue(self.cfg['hanson']['convoy_command'])
        self.assertNotIn('autotest', self.cfg['hanson'])
        self.assertFalse(self.cfg['hanson']['debug_log'])

    def test_turrets(self):
        t = self.cfg['hanson']['turrets']
        self.assertEqual(t['owner'], 4)  # the settlement's player: the defeat rules are not touched
        pts = [(u['x'], u['y']) for u in t['list']]
        self.assertGreaterEqual(len(pts), 12)
        self.assertEqual(len(set(pts)), len(pts))
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                self.assertGreaterEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 3.0, (a, b))  # no overlapping footprints, paths stay open
        roles = {u['role'] for u in t['list']}
        self.assertEqual(roles, set(build.HANSON_ROLES))
        # the turrets are inside the settlement (x 20..72, y 38..60): the far north belongs to the Zerg
        for x, y in pts:
            self.assertTrue(20 <= x <= 72 and 38 <= y <= 60, (x, y))

    def test_validation_rejects_bad_values(self):
        for mutate in (
            lambda c: c['hanson'].update(convoy_command='yes'),
            lambda c: c['hanson']['turrets'].update(owner=2),
            lambda c: c['hanson']['turrets']['list'].append({'x': 1, 'y': 2, 'role': 'moon'}),
            lambda c: c['hanson']['texts'].pop('BtnReady'),
            lambda c: c['hanson']['button'].update(width=5),
            lambda c: c['operatives'].update(squad=['Ghost', 'Ghost', 'Ghost']),
        ):
            bad = copy.deepcopy(self.cfg)
            mutate(bad)
            self.assertTrue(build.validate_config(bad))

    def test_dev_preset_is_hidden(self):
        raw = build.load_json(ADAPTER['config'])
        self.assertTrue(raw['presets']['sniper_dev']['hidden'])
        self.assertEqual([p['name'] for p in launcher_core.profiles_of('thanson01')], ['sniper', 'sniper_next', 'sniper_next_free'])
        self.assertEqual(launcher_core.default_profile('thanson01'), 'sniper')
        self.assertEqual(launcher_core.mission_info('thanson01')['status'], 'Эксперимент')
        dev, _ = build.resolve_config(ADAPTER, 'sniper_dev')
        self.assertTrue(dev['hanson']['debug_log'])
        self.assertEqual(build.validate_config(dev), [])

    def test_free_test_squad_variant(self):
        cfg, _ = build.resolve_config(ADAPTER, 'sniper_next_free')
        self.assertEqual(build.validate_config(cfg), [])
        fs = cfg['hanson']['free_squad']
        self.assertTrue(fs['enabled'])
        self.assertGreater(fs['marines'], 0)
        base, _ = build.resolve_config(ADAPTER, 'sniper_next')
        self.assertNotIn('free_squad', base['hanson'])  # the prepared-detonations variant itself is unchanged
        for key in ('containers', 'convoy_fuel', 'ghost_tuning', 'scenario'):  # sniper rifles, containers, waves and prices are not simplified
            self.assertEqual(cfg[key] if key in cfg else cfg['hanson'].get(key), base[key] if key in base else base['hanson'].get(key), key)
        self.assertIn('go_hFreeMarines = %d;' % fs['marines'], build.gen_hanson(cfg))
        self.assertNotIn('go_hFreeMarines', build.gen_hanson(base))
        card = next(p for p in launcher_core.profiles_of('thanson01') if p['name'] == 'sniper_next_free')
        self.assertEqual(card['label'], 'Тест — бесплатный отряд')
        self.assertIn('%d морпехов' % fs['marines'], card['card'])
        self.assertIn('Тест — бесплатный отряд', launcher_core.detail_lines('thanson01', 'sniper_next_free')[0])
        self.assertNotEqual(build.output_name(ADAPTER, 'sniper_next_free'), build.output_name(ADAPTER, 'sniper_next'))  # a new map file: nothing existing is overwritten

    def test_snipe_fragment_excludes_friendly_targets_only_when_asked(self):
        abil = build.ghost_tuning_fragments(self.cfg['ghost_tuning'])['AbilData.xml']
        self.assertIn('<TargetFilters index="0" value="Biological,Visible;Self,Player,Ally,Neutral,Structure,', abil)
        self.assertIn('<Cooldown TimeUse="1"/>', abil)
        self.assertIn('<Vital index="Energy" value="0"/>', abil)
        eff = build.ghost_tuning_fragments(self.cfg['ghost_tuning'])['EffectData.xml']
        self.assertIn('<Amount value="1000"/>', eff)
        # the other missions' Snipe stays as it was
        tr01, _ = build.resolve_config(build.load_adapter('traynor01'), 'easy')
        self.assertNotIn('TargetFilters', build.ghost_tuning_fragments(tr01['ghost_tuning'])['AbilData.xml'])


class HansonCode(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = build.resolve_config(ADAPTER, 'sniper')
        self.mod = text('core', 'GhostOpsHanson.galaxy')

    def test_block_is_ascii_lint_clean_and_production_has_no_test_code(self):
        block = build.build_block(ADAPTER, self.cfg)
        self.assertTrue(block.isascii())
        self.assertEqual(galaxy_lint.lint(block), [])
        n = len(self.cfg['hanson']['turrets']['list'])
        self.assertIn('go_hTurretX[%d] = ' % (n - 1), block)
        self.assertNotIn('go_hTurretX[%d] = ' % n, block)
        self.assertIn('// no scripted test in this build', block)
        self.assertNotIn('GhostOps_HT_Run', block)
        self.assertNotIn('GhostOps_TacTest', block)  # nothing of the TRaynor02 module
        dev, _ = build.resolve_config(ADAPTER, 'sniper_dev')
        dblock = build.build_block(ADAPTER, dev)
        self.assertTrue(dblock.isascii())
        self.assertEqual(galaxy_lint.lint(dblock), [])
        self.assertIn('GhostOps_HT_Run', dblock)

    def test_hooks(self):
        hooks = {(h['function'], h['where']): h for h in build.hook_list(ADAPTER)}
        self.assertEqual(sorted(hooks), [
            ('gt_ConvoySpawned_Func', 'before'), ('gt_DoomsdayZergAI_Func', 'before'), ('gt_Gathercolonistspriortoevacuation_Func', 'before'),
            ('gt_Initialization_Func', 'before'), ('gt_IntroSequence_Func', 'after')])
        self.assertEqual(hooks[('gt_ConvoySpawned_Func', 'before')]['call'], 'if (GhostOps_Hanson_Hold(TriggerGetCurrent())) { return true; }')
        self.assertEqual(hooks[('gt_IntroSequence_Func', 'after')]['call'], 'GhostOps_OnMissionStart();')

    def test_convoy_command_is_one_shot(self):
        m = self.mod
        click = m.split('bool GhostOps_Hanson_OnClick')[1].split('// Hook in gt_Gathercolonists')[0]
        self.assertIn('(go_hCmdState != 2) || go_hGateOpen', click)  # only a ready convoy, never twice
        self.assertLess(click.index('go_hCmdState = 3;'), click.index('TriggerExecute(go_hGateTrig'))
        hold = m.split('bool GhostOps_Hanson_Hold')[1].split('// Hook (once a second)')[0]
        self.assertIn('go_hGateOpen = false;', hold)  # the gate opens exactly once per click
        self.assertNotIn('Wait(', m.split('// Convoy command (the button)')[1].split('// Explosive containers: placement')[0])  # no thread that a load could cut
        self.assertNotIn('"stop"', m.replace('"stop", 0', ''))  # the original is not held by repeated Stop orders
        # the dialog is created again after a load
        self.assertIn('TriggerAddEventLoadGameDone(go_hLoadTrig)', m)

    def test_nothing_forbidden(self):
        for forbidden in ('UnitKill', 'UnitRemove', 'GameOver', 'libCamp_gf_EndCampaignMission', 'CameraPan', 'UnitSetOwner'):
            self.assertNotIn(forbidden, self.mod)
        adapter = text('adapters', 'thanson01', 'adapter.galaxy')
        self.assertEqual(adapter.count('GhostOps_SpawnOperatives('), 1)
        self.assertIn('if (!GhostOps_ClaimStart())', adapter)
        self.assertLess(adapter.index('GhostOps_ClaimStart'), adapter.index('GhostOps_SpawnOperatives'))

    def test_texts_exist(self):
        block = build.build_block(ADAPTER, self.cfg)
        used = set(re.findall(r'Param/Value/GhostOpsH_(\w+)', self.mod))
        self.assertTrue(used <= set(build.HANSON_TEXT_KEYS) | set(build.HANSON_EXTRA_TEXT_KEYS) | {'L_'}, used)
        ent = dict(build.text_entries(self.cfg)['ruRU'])
        for k in used:
            if k not in build.HANSON_EXTRA_TEXT_KEYS and k != 'L_':  # the extra texts belong to the prepared-detonation profile only (checked in test_th01_next)
                self.assertIn(build.HANSON_TEXT_PREFIX + k, ent)
        self.assertTrue(block.isascii())

    @unittest.skipUnless(os.path.isfile(SRC), 'source map not extracted')
    def test_real_map_builds_and_verifies(self):
        for preset in ('sniper', 'sniper_dev'):
            ns = argparse.Namespace(mission='thanson01', preset=preset, diag=False, multiplier=None, source=None)
            self.assertEqual(build.cmd_build(ns), 0, preset)
        man = json.loads(build.read(build.build_manifest_path('thanson01_sniper'), 'r'))
        self.assertEqual(man['audio'], [])
        arc = sc2mpq.Archive(build.read(os.path.join(ROOT, 'dist', 'GhostOps_THanson01_sniper.SC2Map')))
        script = arc.read('MapScript.galaxy').decode('utf-8-sig')
        self.assertEqual(script.count(build.HOOK_TAG), 5)
        self.assertEqual(script.count('GhostOps_Hanson_Hold(TriggerGetCurrent())'), 1)


if __name__ == '__main__':
    unittest.main()
