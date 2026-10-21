import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402

OTHER = ('config/traynor02.poc.json', 'config/ttychus01.json')


def jsn(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return json.load(f)


class GhostTuning(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = build.resolve_config(jsn('adapters', 'traynor01', 'adapter.json'), 'easy')
        self.gt = self.cfg['ghost_tuning']

    def test_values_requested_by_the_owner(self):
        gt = self.gt
        self.assertEqual((gt['energy_start'], gt['energy_max']), (100, 100))
        self.assertEqual(gt['regen_per_second'], 20)
        self.assertEqual(gt['cloak_activation_cost'], 0)
        self.assertEqual(gt['cloak_net_per_second'], -10)
        self.assertEqual(gt['snipe'], {'cost': 10, 'damage': 45, 'cast_time': 0.3, 'cooldown': 0})  # easy profile
        self.assertEqual(build.validate_config(self.cfg), [])

    def test_fragments_sum_to_the_requested_energy_flow(self):
        fr = build.ghost_tuning_fragments(self.gt)
        self.assertEqual(sorted(fr), ['AbilData.xml', 'BehaviorData.xml', 'EffectData.xml', 'UnitData.xml'])
        parsed = {k: ET.fromstring('<Catalog>' + v + '</Catalog>') for k, v in fr.items()}
        unit = parsed['UnitData.xml'].find('CUnit')
        self.assertEqual(unit.get('id'), 'Ghost')
        regen = float(unit.find('EnergyRegenRate').get('value'))
        self.assertEqual(float(unit.find('EnergyStart').get('value')), 100)
        self.assertEqual(float(unit.find('EnergyMax').get('value')), 100)
        beh = parsed['BehaviorData.xml'].find('CBehaviorBuff')
        self.assertEqual(beh.get('id'), 'GhostCloak')
        drain = float(beh.find('Modification').find('VitalRegenArray').get('value'))
        self.assertEqual(regen, 20)
        self.assertEqual(regen + drain, -10)  # net under cloak: no regeneration while cloaked
        self.assertEqual(drain, -30)
        # outside the cloak the unit regenerates at the plain regen: +20 per second
        self.assertEqual(100 / regen, 5)  # 0 -> 100 energy in 5 s
        self.assertEqual(100 / -(regen + drain), 10)  # 100 energy of cloak last 10 s

    def test_snipe_and_cloak_costs(self):
        ab = ET.fromstring('<Catalog>' + build.ghost_tuning_fragments(self.gt)['AbilData.xml'] + '</Catalog>')
        by_id = {e.get('id'): e for e in ab}
        cloak = by_id['GhostCloak']
        self.assertEqual(float(cloak.find('Cost').find('Vital').get('value')), 0)
        snipe = by_id['Snipe']
        self.assertEqual(float(snipe.find('Cost').find('Vital').get('value')), 10)
        self.assertEqual(float(snipe.find('CastIntroTime').get('value')), 0.3)
        self.assertIsNone(snipe.find('Range'))  # range, target filters, visibility rules stay as in the game
        self.assertIsNone(snipe.find('TargetFilters'))
        self.assertIsNone(snipe.find('Cooldown'))
        eff = ET.fromstring('<Catalog>' + build.ghost_tuning_fragments(self.gt)['EffectData.xml'] + '</Catalog>').find('CEffectDamage')
        self.assertEqual(float(eff.find('Amount').get('value')), 45)
        self.assertEqual(eff.get('id'), 'SnipeDamage')  # the standard Ghost Snipe, not Nova's
        self.assertNotIn('Nova', build.ghost_tuning_fragments(self.gt)['AbilData.xml'])

    def test_rifle_and_other_things_are_not_touched(self):
        text = ''.join(build.ghost_tuning_fragments(self.gt).values())
        for forbidden in ('Weapon', 'Life', 'Speed', 'Armor', 'CUnit id="Medic"', 'Raynor', 'Marine'):
            self.assertNotIn(forbidden, text)

    def test_validation(self):
        for key, bad in (('energy_max', 0), ('regen_per_second', -1), ('cloak_net_per_second', 25),
                         ('cloak_net_per_second', 'fast'), ('energy_start', 150), ('cloak_activation_cost', True)):
            c = json.loads(json.dumps(self.cfg))
            c['ghost_tuning'][key] = bad
            self.assertTrue(build.validate_config(c), (key, bad))
        c = json.loads(json.dumps(self.cfg))
        c['ghost_tuning']['snipe']['damage'] = 0
        self.assertTrue(build.validate_config(c))
        del c['ghost_tuning']['snipe']
        self.assertTrue(build.validate_config(c))

    def test_only_traynor01_has_tuning(self):
        for path in OTHER:
            c = jsn(path)
            self.assertNotIn('ghost_tuning', c, path)
            joined = ''.join(build.catalog_fragments(c).values())
            for marker in ('EnergyRegenRate', 'SnipeDamage', 'GhostCloak'):
                self.assertNotIn(marker, joined, path)  # only the Nova hold-fire patch is generated there
        self.assertEqual(sorted(build.catalog_fragments(self.cfg)), ['AbilData.xml', 'BehaviorData.xml', 'EffectData.xml', 'SoundData.xml', 'UnitData.xml'])

    def test_catalog_patch_creates_missing_files_and_restores(self):
        frag = build.ghost_tuning_fragments(self.gt)['AbilData.xml']
        new = build.patch_unitdata(build.NEW_CATALOG, frag)
        ET.fromstring(new.encode('utf-8'))
        self.assertEqual(build.unpatch_unitdata(new), build.NEW_CATALOG)
        existing = '<?xml version="1.0" encoding="us-ascii"?>\r\n<Catalog>\r\n    <CUnit id="X"/>\r\n</Catalog>\r\n'
        self.assertEqual(build.unpatch_unitdata(build.patch_unitdata(existing, frag)), existing)
        with self.assertRaises(ValueError):
            build.patch_unitdata('<Catalog><CAbilEffectTarget id="Snipe"/></Catalog>', frag)  # map already defines Snipe
        with self.assertRaises(ValueError):
            build.patch_unitdata(new, frag)

    def test_emp_and_nuke_are_removed_individually_not_snipe_or_cloak(self):
        self.assertEqual(self.gt['remove_abilities'], ['TacNukeStrike', 'EMP'])
        unit = ET.fromstring('<Catalog>' + build.ghost_tuning_fragments(self.gt)['UnitData.xml'] + '</Catalog>').find('CUnit')
        removed = {int(a.get('index')): a.get('removed') for a in unit.iter('AbilArray')}
        # indices in the standard Ghost AbilArray: stop 0, attack 1, move 2, GhostCloak 3, Snipe 4,
        # TacNukeStrike 5, GhostHoldFire 6, EMP 7, GhostWeaponsFree 8
        self.assertEqual(removed, {5: '1', 7: '1'})
        self.assertEqual(build.GHOST_ABIL_INDEX, {'TacNukeStrike': 5, 'EMP': 7})
        for forbidden in ('GhostCloak', 'Snipe', 'GhostHoldFire', 'GhostWeaponsFree', 'Link='):
            self.assertNotIn(forbidden, build.ghost_tuning_fragments(self.gt)['UnitData.xml'])
        # the general player-level ban that hid the cloak button is not used
        self.assertEqual(self.cfg['operatives']['disabled_abilities'], [])
        self.assertNotIn('TechTreeAbilityAllow(lp_player, AbilityCommand("EMP"', build.gen_config(self.cfg))
        for bad in (['Snipe'], ['GhostCloak'], ['EMP', 'EMP']):
            c = json.loads(json.dumps(self.cfg))
            c['ghost_tuning']['remove_abilities'] = bad
            self.assertTrue(build.validate_config(c), bad)

    def test_raynor_and_marine_life_rules(self):
        fus = {f['type']: f['max_life'] for f in self.cfg['army']['fragile_units']}
        self.assertEqual(fus, {'Marine': 1, 'Raynor01': 45})
        self.assertEqual(self.cfg['operatives']['squad'], ['Ghost', 'Ghost'])  # no Medic created
        g = build.gen_config(self.cfg)
        self.assertNotIn('Medic', g)

    def test_core_shows_catalog_values_in_game(self):
        with open(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), encoding='utf-8') as f:
            core = f.read()
        for field in ('"EnergyMax"', '"EnergyRegenRate"', '"Cost[0].Vital[Energy]"', '"CastIntroTime"', '"Amount"'):
            self.assertIn(field, core)
        self.assertTrue(re.search(r'if \(go_cfgShowTuning\)', core))


if __name__ == '__main__':
    unittest.main()
