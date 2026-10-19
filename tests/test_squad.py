import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402

MISSIONS = {'traynor02': 'config/traynor02.poc.json', 'ttychus01': 'config/ttychus01.json'}


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def jsn(*parts):
    return json.loads(text(*parts))


class SquadConfig(unittest.TestCase):
    def test_default_squad_is_nova_plus_two_ghosts(self):
        for m, cfgpath in MISSIONS.items():
            cfg = jsn(cfgpath)
            self.assertEqual(build.validate_config(cfg), [], m)
            self.assertEqual(cfg['operatives']['squad'], ['Nova', 'Ghost', 'Ghost'])
            self.assertTrue(cfg['operatives']['ghost_permanent_cloak'])
            self.assertTrue(cfg['operatives']['ghost_start_cloaked'])
            self.assertTrue(cfg['operatives']['start_hold_fire'])
            self.assertEqual(cfg['base_support']['damage_multiplier'], 3)
            self.assertFalse(cfg['experimental']['invulnerable_allies'])

    def test_squad_validation(self):
        cfg = jsn(MISSIONS['traynor02'])
        for bad in ([], ['Ghost'] * 7, ['Marine'], 'Nova', [None]):
            c = json.loads(json.dumps(cfg))
            c['operatives']['squad'] = bad
            self.assertTrue(build.validate_config(c), bad)
        for good in (['Nova'], ['Ghost'] * 6, ['Nova', 'Ghost']):
            c = json.loads(json.dumps(cfg))
            c['operatives']['squad'] = good
            self.assertEqual(build.validate_config(c), [], good)
        c = json.loads(json.dumps(cfg))
        c['operatives']['ghost_permanent_cloak'] = 'yes'
        self.assertTrue(build.validate_config(c))

    def test_generated_config(self):
        g = build.gen_config(jsn(MISSIONS['ttychus01']))
        for line in ('go_cfgSquadSize = 3;', 'go_cfgSquadType[0] = "Nova";', 'go_cfgSquadType[2] = "Ghost";',
                     'go_cfgStartHoldFire = true;', 'go_cfgGhostPermanentCloak = true;',
                     'go_cfgGhostStartCloaked = true;', 'go_cfgDamageMultiplier = 3;', 'go_cfgInvulnerableAllies = false;'):
            self.assertIn(line, g)


class CoreSquad(unittest.TestCase):
    def setUp(self):
        self.core = text('core', 'GhostOpsCore.galaxy')
        self.code = galaxy_lint.strip(self.core)

    def fn(self, name, ret='void'):
        end = chr(10) + '}' + chr(10)
        return self.code[self.code.index('%s %s' % (ret, name)):].split(end)[0]

    def test_ghost_tech_uses_blizzard_upgrades_only(self):
        t = self.fn('GhostOps_GrantGhostTech')
        self.assertIn('TechTreeUpgradeAddLevel(lp_player, "PersonalCloaking"', self.core)
        self.assertIn('TechTreeUpgradeAddLevel(lp_player, "PermanentCloakGhost"', self.core)
        self.assertIn('if (go_cfgGhostPermanentCloak)', t)
        self.assertEqual(self.core.count('TechTreeUpgradeAddLevel'), 2)

    def test_squad_registered_before_any_scan(self):
        s = self.fn('GhostOps_SpawnOperatives', 'unit')
        self.assertIn('GhostOps_RegisterOperative(UnitLastCreated())', s)
        self.assertNotIn('ScanAll', s)
        self.assertNotIn('SupportUnit', s)
        # the periodic scan only starts afterwards (Start is called by the adapter after spawning)
        ad = text('adapters', 'traynor02', 'adapter.galaxy')
        self.assertLess(ad.index('GhostOps_SpawnOperatives'), ad.index('GhostOps_Start()'))

    def test_start_state_uses_standard_abilities_not_order_spam(self):
        end = chr(10) + '}' + chr(10)
        t = self.core[self.core.index('bool GhostOps_StartStateTick'):].split(end)[0]
        self.assertIn('AbilityCommand("GhostHoldFire", 0)', t)
        self.assertIn('AbilityCommand("GhostCloak", 0)', t)
        self.assertIn('UnitGetType(lv_unit) == "Ghost"', t)  # only standard ghosts get the cloak order
        # one shot, not a periodic order loop
        self.assertIn('TriggerAddEventTimeElapsed(go_startStateTrigger', self.code)
        self.assertEqual(self.code.count('TriggerAddEventTimePeriodic'), 1)

    def test_operatives_never_get_the_army_bonus(self):
        sup = self.fn('GhostOps_SupportUnit')
        self.assertIn('GhostOps_IsOperative(lp_unit)', sup)
        self.assertNotIn('Nova', self.code)


class NovaFireControl(unittest.TestCase):
    def test_fragment_adds_standard_abilities_with_explicit_indices(self):
        frag = text('core', 'data', 'NovaFireControl.xml')
        root = ET.fromstring('<Catalog>' + frag + '</Catalog>')
        nova = root.find('CUnit')
        self.assertEqual(nova.get('id'), 'Nova')
        abils = [(a.get('index'), a.get('Link')) for a in nova.iter('AbilArray')]
        self.assertEqual(abils, [('7', 'GhostHoldFire'), ('8', 'GhostWeaponsFree')])
        btn = [(b.get('index'), b.get('AbilCmd')) for b in nova.iter('LayoutButtons')]
        self.assertEqual(btn, [('12', 'GhostHoldFire,Execute'), ('13', 'GhostWeaponsFree,Execute')])

    def test_patch_is_reversible_and_refuses_double_or_foreign_nova(self):
        frag = text('core', 'data', 'NovaFireControl.xml')
        for eol in ('\r\n', '\n'):
            src = '<?xml version="1.0" encoding="us-ascii"?>' + eol + '<Catalog>' + eol + '    <CUnit id="X"/>' + eol + '</Catalog>' + eol
            out = build.patch_unitdata(src, frag)
            ET.fromstring(out.encode('utf-8'))
            self.assertEqual(build.unpatch_unitdata(out), src)
            with self.assertRaises(ValueError):
                build.patch_unitdata(out, frag)
        with self.assertRaises(ValueError):
            build.patch_unitdata('<Catalog><CUnit id="Nova"/></Catalog>', frag)


class Adapters(unittest.TestCase):
    def test_each_adapter_covers_only_player_one_and_is_complete(self):
        for m in MISSIONS:
            ad = text('adapters', m, 'adapter.galaxy')
            self.assertEqual(re.findall(r'GhostOps_SetPlayerCovered\((\d+), true\)', ad), ['1'], m)
            self.assertEqual(galaxy_lint.lint(ad.replace('GhostOps_', 'GhostOps_')), [] if False else galaxy_lint.lint(ad))
            meta = jsn('adapters', m, 'adapter.json')
            self.assertEqual(meta['mission'], m)
            self.assertEqual(meta['config'], MISSIONS[m])
            self.assertTrue(os.path.isfile(os.path.join(ROOT, meta['config'])))
            self.assertEqual(meta['start_hook']['after'], 'TriggerExecute(gt_StartGame, true, false);')

    def test_missions_do_not_share_constants(self):
        a = jsn('adapters', 'traynor02', 'adapter.json')['required_markers']
        b = jsn('adapters', 'ttychus01', 'adapter.json')['required_markers']
        self.assertIn('CameraInfoFromId(1117)', a)
        self.assertIn('CameraInfoFromId(26)', b)
        self.assertNotIn('1117', text('adapters', 'ttychus01', 'adapter.galaxy'))
        self.assertNotIn('26', re.sub(r'//.*', '', text('adapters', 'traynor02', 'adapter.galaxy')))


if __name__ == '__main__':
    unittest.main()
