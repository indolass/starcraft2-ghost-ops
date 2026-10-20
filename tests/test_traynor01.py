import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402

OTHER_MISSIONS = {'traynor02': 'config/traynor02.poc.json', 'ttychus01': 'config/ttychus01.json'}


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def jsn(*parts):
    return json.loads(text(*parts))


class TRaynor01(unittest.TestCase):
    def setUp(self):
        self.adapter = jsn('adapters', 'traynor01', 'adapter.json')
        self.cfg, _ = build.resolve_config(self.adapter, 'easy')
        self.core = text('core', 'GhostOpsCore.galaxy')

    def test_config_is_valid_and_separate(self):
        self.assertEqual(build.validate_config(self.cfg), [])
        op = self.cfg['operatives']
        self.assertEqual(op['squad'], ['Ghost', 'Ghost'])  # no Nova, and no Medic since the easy-variant iteration
        self.assertFalse(op['ghost_permanent_cloak'])  # no Crius Suit, normal cloak cost
        # ability bans via TechTreeAbilityAllow also hid the cloak button (Owner test), and the Owner now
        # explicitly allows the standard Ghost Snipe, so nothing is banned at the moment
        self.assertEqual(op['disabled_abilities'], [])
        self.assertEqual(self.cfg['base_support']['damage_multiplier'], 1)
        self.assertFalse(self.cfg['experimental']['invulnerable_allies'])
        self.assertEqual(self.cfg['difficulty']['expected'], 3)
        self.assertEqual(self.cfg['army']['fragile_units'], [{'type': 'Marine', 'max_life': 1}, {'type': 'Raynor01', 'max_life': 45}])
        self.assertEqual(self.cfg['ghost_tuning']['remove_abilities'], ['TacNukeStrike', 'EMP'])
        self.assertFalse(build.needs_nova_patch(self.cfg))  # no Nova data override in this map

    def test_other_missions_keep_their_settings(self):
        for m, path in OTHER_MISSIONS.items():
            c = jsn(path)
            self.assertEqual(c['operatives']['squad'], ['Nova', 'Ghost', 'Ghost', 'Medic', 'Medic'], m)
            self.assertEqual(c['base_support']['damage_multiplier'], 3, m)
            self.assertTrue(c['operatives']['ghost_permanent_cloak'], m)
            self.assertNotIn('army', c)  # fragile marines are a TRaynor01-only setting
            self.assertNotIn('disabled_abilities', c['operatives'])

    def test_generated_config(self):
        g = build.gen_config(self.cfg)
        self.assertIn('go_cfgSquadSize = 2;', g)
        self.assertNotIn('Medic', g)
        self.assertIn('go_cfgFragileCount = 2;', g)
        self.assertIn('go_cfgFragileType[0] = "Marine";', g)
        self.assertIn('go_cfgFragileLife[0] = 1.0;', g)
        self.assertIn('go_cfgFragileType[1] = "Raynor01";', g)
        self.assertIn('go_cfgFragileLife[1] = 45.0;', g)
        self.assertIn('go_cfgDamageMultiplier = 1;', g)
        self.assertIn('go_cfgGhostPermanentCloak = false;', g)
        self.assertNotIn('TechTreeAbilityAllow', g)
        self.assertIn('go_cfgShowTuning = true;', g)
        banned = json.loads(json.dumps(self.cfg))
        banned['operatives']['disabled_abilities'] = ['Snipe', 'EMP', 'TacNukeStrike']
        for ab in ('Snipe', 'EMP', 'TacNukeStrike'):  # the mechanism itself still works
            self.assertIn('TechTreeAbilityAllow(lp_player, AbilityCommand("%s", 0), false);' % ab, build.gen_config(banned))
        other = build.gen_config(jsn(OTHER_MISSIONS['traynor02']))
        self.assertIn('go_cfgFragileCount = 0;', other)
        self.assertIn('go_cfgShowTuning = false;', other)
        self.assertNotIn('TechTreeAbilityAllow', other)

    def test_validation_of_new_keys(self):
        for bad in (['Snipe', 'Snipe'], ['Blink'], 'Snipe'):
            c = json.loads(json.dumps(self.cfg))
            c['operatives']['disabled_abilities'] = bad
            self.assertTrue(build.validate_config(c), bad)
        for bad in ({'type': 'Marine', 'max_life': 0}, {'type': 'Mar ine', 'max_life': 1}, {'type': 'Marine'}, 5):
            c = json.loads(json.dumps(self.cfg))
            c['army']['fragile_units'] = [bad]
            self.assertTrue(build.validate_config(c), bad)
        c = json.loads(json.dumps(self.cfg))
        c['army']['fragile_units'] = [{'type': 'Marine', 'max_life': 1}] * 2
        self.assertTrue(build.validate_config(c))  # duplicate types
        c['army']['fragile_units'] = [{'type': 'T%d' % i, 'max_life': 1} for i in range(5)]
        self.assertTrue(build.validate_config(c))  # more than the supported 4

    def test_hooks_cover_both_intro_branches_once(self):
        hooks = build.hook_list(self.adapter)
        funcs = sorted(h['function'] for h in hooks)
        self.assertEqual(funcs, ['gt_Initialization_Func', 'gt_IntroCleanupEscape_Func', 'gt_IntroCleanupNoEscape_Func', 'gt_OpeningLineQ_Func'])
        self.assertEqual([h['where'] for h in hooks if h['function'] == 'gt_Initialization_Func'], ['before'])
        ad = text('adapters', 'traynor01', 'adapter.galaxy')
        self.assertIn('if (!GhostOps_ClaimStart())', ad)  # watch and skip branches create the squad once
        self.assertLess(ad.index('GhostOps_ClaimStart'), ad.index('GhostOps_SpawnOperatives'))
        self.assertEqual(re.findall(r'GhostOps_SetPlayerCovered\((\d+), true\)', ad), ['1'])
        self.assertNotIn('UnitSelect', ad)  # the player's selection and the original Raynor are left alone

    def test_patch_on_synthetic_script_places_all_hooks_and_restores(self):
        nl = chr(13) + chr(10)
        src = nl.join([
            'include "TriggerLibs/NativeLib"', 'include "TriggerLibs/CampaignLib"', '',
            'void InitLibs () {', '}', '',
            'bool gt_Initialization_Func (bool testConds, bool runActions) {',
            '    // Actions', '    libCamp_gf_LoadCampaignData(1);', '    return true;', '}', '',
            'bool gt_IntroCleanupNoEscape_Func (bool testConds, bool runActions) {',
            '    PointFromId(505);', '    TriggerExecute(gt_StartGame, true, false);', '    return true;', '}', '',
            'bool gt_IntroCleanupEscape_Func (bool testConds, bool runActions) {',
            '    TriggerExecute(gt_StartGame, true, false);', '    return true;', '}', '',
            'bool gt_OpeningLineQ_Func (bool testConds, bool runActions) {',
            '    TriggerQueueEnter();', '    libCamp_gf_SetAllSoundChannelVolumesCampaign(2);', '    TriggerQueueExit();', '    return true;', '}', '', 'trigger gt_StartGame;', ''])
        block = build.build_block(self.adapter, self.cfg)
        out = build.patch_script(src, self.adapter, block)
        self.assertEqual(out.count(build.HOOK_TAG), 4)
        self.assertIn('GhostOps_T1_OnOpeningLine(gv_raynor);' + build.HOOK_TAG, out)
        self.assertEqual(out.count('GhostOps_OnMissionStart();' + build.HOOK_TAG), 2)
        self.assertLess(out.index('GhostOps_CaptureInit();' + build.HOOK_TAG), out.index('libCamp_gf_LoadCampaignData(1);'))
        self.assertEqual(galaxy_lint.lint(out), [])
        s = re.sub(re.escape(nl) + re.escape(build.BEGIN) + '.*?' + re.escape(build.END), '', out, flags=re.S)
        s = re.sub(r'\r?\n    GhostOps_\w+\([^\n]*\);' + re.escape(build.HOOK_TAG), '', s)
        self.assertEqual(s, src)
        with self.assertRaises(ValueError):
            build.patch_script(src.replace('libCamp_gf_LoadCampaignData(1);', ''), self.adapter, block)

    def test_core_rules_for_fragile_units_and_restrictions(self):
        code = galaxy_lint.strip(self.core)
        end = chr(10) + '}' + chr(10)
        scan = code[code.index('void GhostOps_FragileScan'):].split(end)[0]
        self.assertIn('go_playerCovered[lv_p]', scan)  # only covered players: enemy marines are never touched
        self.assertIn('UnitGetPropertyFixed(lv_unit, c_unitPropLifeMax, c_unitPropCurrent) > go_cfgFragileLife[lv_k]', scan)
        self.assertIn('UnitSetPropertyFixed(lv_unit, c_unitPropLifeMax, go_cfgFragileLife[lv_k])', scan)  # maximum life
        self.assertNotIn('Raynor', code)  # unit types come from the config, never from Core
        self.assertNotIn('UnitKill', code)
        self.assertNotIn('UnitRemove', code)
        self.assertNotIn('c_unitPropLifePercent', code)  # no periodic restoring of current health
        start = code[code.index('void GhostOps_Start'):].split(end)[0]
        self.assertIn('go_cfgFragileCount > 0', start)  # the scan only runs when configured
        spawn = code[code.index('unit GhostOps_SpawnOperatives'):].split(end)[0]
        self.assertIn('GhostOps_ApplyAbilityRestrictions(lp_player)', spawn)

    def test_difficulty_is_captured_before_init_triggers(self):
        self.assertIn('go_initDifficulty = PlayerDifficulty(1);', self.core)
        init = self.adapter['init_hook']
        self.assertEqual(init['call'], 'GhostOps_CaptureInit();')
        self.assertEqual(init['before'], 'libCamp_gf_LoadCampaignData(1);')


if __name__ == '__main__':
    unittest.main()
