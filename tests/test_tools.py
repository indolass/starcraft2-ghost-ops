import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402
import sc2mpq  # noqa: E402

SYNTH = (
    'include "TriggerLibs/NativeLib"\r\ninclude "TriggerLibs/CampaignLib"\r\n\r\n'
    'void InitLibs () {\r\n    libNtve_InitLib();\r\n}\r\n\r\n'
    'trigger gt_StartGame;\r\n'
    'bool gt_IntroSequence_Func (bool testConds, bool runActions) {\r\n'
    '    CameraInfoGetTarget(CameraInfoFromId(1117));\r\n'
    '    TriggerExecute(gt_StartGame, true, false);\r\n'
    '    return true;\r\n}\r\n'
)


class MpqTests(unittest.TestCase):
    def test_roundtrip_and_modify(self):
        files = {'MapScript.galaxy': SYNTH.encode(), 'Objects': b'x' * 10000, 'DocumentInfo': b'<a/>'}
        a = sc2mpq.Archive(sc2mpq.create(files))
        for k, v in files.items():
            self.assertEqual(a.read(k), v)
        a.set_file('MapScript.galaxy', b'new')
        a.set_file('Extra.txt', b'added')
        b = sc2mpq.Archive(a.tobytes())
        self.assertEqual(b.read('MapScript.galaxy'), b'new')
        self.assertEqual(b.read('Extra.txt'), b'added')
        self.assertEqual(b.read('Objects'), files['Objects'])
        self.assertEqual(b.read('DocumentInfo'), b'<a/>')
        self.assertIsNone(b.read('nope'))


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.adapter = json.load(open(os.path.join(ROOT, 'adapters', 'traynor02', 'adapter.json'), encoding='utf-8'))
        self.adapter['required_markers'] = ['gt_StartGame', 'gt_IntroSequence_Func', 'CameraInfoFromId(1117)', 'void InitLibs']
        self.adapter['start_hooks'] = self.adapter['start_hooks'][:1]  # the synthetic script only has the intro function
        self.cfg = json.load(open(os.path.join(ROOT, 'config', 'traynor02.poc.json'), encoding='utf-8'))

    def cfg_with(self, **kw):
        c = json.loads(json.dumps(self.cfg))
        for k, v in kw.items():
            sect, key = k.split('__')
            c[sect][key] = v
        return c

    def test_config_valid(self):
        self.assertEqual(build.validate_config(self.cfg), [])
        self.assertEqual(self.cfg['base_support']['damage_multiplier'], 3)
        self.assertFalse(self.cfg['experimental']['invulnerable_allies'])
        bad = json.loads(json.dumps(self.cfg))
        bad['nukes_granted'] = 3
        self.assertTrue(build.validate_config(bad))

    def test_multiplier_values(self):
        for m in (1, 2, 3):
            c = self.cfg_with(base_support__damage_multiplier=m)
            self.assertEqual(build.validate_config(c), [])
            self.assertIn('go_cfgDamageMultiplier = %d;' % m, build.gen_config(c))
        for m in (0, 4, True, '3', None):
            self.assertTrue(build.validate_config(self.cfg_with(base_support__damage_multiplier=m)), m)

    def test_models_are_not_combined(self):
        both = self.cfg_with(experimental__invulnerable_allies=True)
        self.assertTrue(build.validate_config(both))
        only_inv = self.cfg_with(experimental__invulnerable_allies=True, base_support__damage_multiplier=1)
        self.assertEqual(build.validate_config(only_inv), [])
        self.assertIn('go_cfgInvulnerableAllies = true;', build.gen_config(only_inv))
        self.assertIn('go_cfgInvulnerableAllies = false;', build.gen_config(self.cfg))

    def test_old_schema_rejected(self):
        old = json.loads(json.dumps(self.cfg))
        old['schema_version'] = 1
        self.assertTrue(build.validate_config(old))

    def test_build_is_reproducible(self):
        block = build.build_block(self.adapter, self.cfg)
        self.assertEqual(build.patch_script(SYNTH, self.adapter, block), build.patch_script(SYNTH, self.adapter, block))
        files = {'a': b'x' * 5000, 'b': b'y'}
        self.assertEqual(sc2mpq.create(files), sc2mpq.create(files))

    def test_patch_is_reversible_and_lints(self):
        block = build.build_block(self.adapter, self.cfg)
        self.assertEqual(galaxy_lint.lint(block), [])
        out = build.patch_script(SYNTH, self.adapter, block)
        self.assertEqual(out.count(build.HOOK_TAG), 1)
        self.assertLess(out.index(build.BEGIN), out.index('void InitLibs'))
        self.assertEqual(galaxy_lint.lint(out), [])
        import re
        s = re.sub(r'\r?\n' + re.escape(build.BEGIN) + r'.*?' + re.escape(build.END), '', out, flags=re.S)
        s = re.sub(r'\r?\n    GhostOps_OnMissionStart\(\);' + re.escape(build.HOOK_TAG), '', s)
        self.assertEqual(s, SYNTH)

    def test_refuses_double_patch_and_missing_anchor(self):
        block = build.build_block(self.adapter, self.cfg)
        once = build.patch_script(SYNTH, self.adapter, block)
        with self.assertRaises(ValueError):
            build.patch_script(once, self.adapter, block)
        with self.assertRaises(ValueError):
            build.patch_script(SYNTH.replace('TriggerExecute(gt_StartGame, true, false);', ''), self.adapter, block)

    def test_core_rules(self):
        core = open(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), encoding='utf-8').read()
        code = galaxy_lint.strip(core)
        self.assertNotIn('Nova', code)  # operatives come from the registry, not from a type name
        end = chr(10) + '}' + chr(10)

        def fn(name):
            return code[code.index('void ' + name):].split(end)[0]
        # operatives are excluded from both models through the registry
        self.assertIn('GhostOps_IsOperative(lp_unit)', fn('GhostOps_SupportUnit'))
        self.assertIn('GhostOps_IsOperative(lp_unit)', fn('GhostOps_ShieldUnit'))
        # one buff per unit: the behaviour is added only behind the supported-group check
        sup = fn('GhostOps_SupportUnit')
        self.assertLess(sup.index('UnitGroupHasUnit(go_supported'), sup.index('UnitBehaviorAdd'))
        self.assertEqual(code.count('UnitBehaviorAdd'), 1)
        self.assertEqual(core.count('"DamageDealtDouble"'), 1)
        self.assertEqual(core.count('"DamageDealtMega"'), 1)
        # invulnerability is only ever set inside the experimental shield, behind the config flag
        self.assertEqual(code.count('UnitSetState(lp_unit, c_unitStateInvulnerable, true)'), 1)
        self.assertEqual(code.count('c_unitStateInvulnerable, true'), 1)
        scan = fn('GhostOps_ScanPlayer')
        self.assertIn('if (go_cfgInvulnerableAllies)', scan)
        # structures are not buffed automatically
        self.assertIn('c_targetFilterStructure', scan.split('if (go_cfgInvulnerableAllies)')[0])
        # mission-made invulnerability is respected
        self.assertIn('UnitTestState(lp_unit, c_unitStateInvulnerable)', fn('GhostOps_ShieldUnit'))
        # new units: periodic scan
        self.assertIn('TriggerAddEventTimePeriodic', code)

    def test_adapter_covers_only_player_one(self):
        ad = open(os.path.join(ROOT, 'adapters', 'traynor02', 'adapter.galaxy'), encoding='utf-8').read()
        import re
        covered = re.findall(r'GhostOps_SetPlayerCovered\((\d+), true\)', ad)
        self.assertEqual(covered, ['1'])

    def test_lint_detects_problems(self):
        self.assertTrue(galaxy_lint.lint('void GhostOps_A () { GhostOps_B(); }'))
        self.assertTrue(galaxy_lint.lint('void GhostOps_A () {'))


if __name__ == '__main__':
    unittest.main()
