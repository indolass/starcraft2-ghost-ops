"""TTychus01 "Grab and run" free test (config key "tychus", core/GhostOpsTychus.galaxy): configuration, catalog data, hooks, texts, the card, a real build.
The settings checked here are the EXPERIMENTAL first values of the agreed design (never Owner-approved numbers)."""
import argparse
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build  # noqa: E402
import launcher_core  # noqa: E402
import sc2mpq  # noqa: E402

ADAPTER = build.load_adapter('ttychus01')
SRC = os.path.join(ROOT, 'tmp', 'source', 'TTychus01.SC2Map')


def cfg(preset):
    return build.resolve_config(ADAPTER, preset)[0]


class Settings(unittest.TestCase):
    def test_the_presets_validate_and_the_old_prototype_is_kept(self):
        raw = build.load_json('config/ttychus01.json')
        self.assertEqual(list(raw['presets']), ['prototype', 'probe_dev', 'grab_free', 'grab_free_dev'])
        self.assertEqual(raw['default_preset'], 'grab_free')
        for p in raw['presets']:
            self.assertEqual(build.validate_config(cfg(p)), [], p)
        self.assertNotIn('tychus', cfg('prototype'))
        self.assertEqual(cfg('prototype')['operatives']['squad'], ['Nova', 'Ghost', 'Ghost', 'Medic', 'Medic'])  # the early prototype is unchanged
        self.assertTrue(raw['presets']['grab_free_dev']['hidden'])
        self.assertTrue(raw['presets']['probe_dev']['hidden'])

    def test_totals_kits_and_normal_unit_stats(self):
        c = cfg('grab_free')
        t = c['tychus']
        self.assertEqual(t['totals'], {'scvs': 12, 'marines': 8, 'medics': 2, 'ghosts': 2, 'marauders': 3})
        self.assertEqual(t['kits'], {'turret': 2, 'bunker': 2})
        self.assertTrue(t['allow_refinery'])
        self.assertEqual(c['operatives']['squad'], ['Ghost', 'Ghost'])
        self.assertEqual(c['base_support']['damage_multiplier'], 1)  # no x3: normal unit stats
        self.assertNotIn('ghost_life', c['ghost_tuning'])  # stock Ghost health
        self.assertEqual(build.effective_fragile_units(c), [])

    def test_the_agreed_experimental_numbers(self):
        t = cfg('grab_free')['tychus']
        d = t['decoy']
        self.assertEqual((d['range'], d['radius'], d['charges'], d['recharge'], d['life'], d['rage']), (15, 7, 2, 12, 25, 4))
        self.assertEqual(t['artifact']['extract_seconds'], 5)
        self.assertEqual(t['evac']['window'], 90)
        self.assertEqual(cfg('grab_free')['fold']['duration'], 8)
        self.assertTrue(t['guardians']['immune_to_player'] and t['guardians']['prefer_zerg'])

    def test_the_shared_mechanics_of_the_missions_are_set_explicitly(self):
        c = cfg('grab_free')
        self.assertTrue(c['operatives']['ghost_permanent_cloak'])
        self.assertTrue(c['detector_analysis']['enabled'] and c['detector_analysis']['early_warning']['enabled'])
        self.assertTrue(c['ghost_tuning']['fire_control']['enabled'])
        self.assertNotIn('rifle_shot', c['ghost_tuning']['snipe'])  # the stock Snipe control
        self.assertEqual(c['tychus']['salvo']['hotkey'], 'A')
        self.assertTrue(c['fold']['turret'] and c['fold']['bunker'])

    def test_a_bad_value_is_refused(self):
        c = cfg('grab_free')
        c['tychus']['decoy']['radius'] = 0
        self.assertTrue(any('decoy.radius' in e for e in build.validate_tychus(c)))
        c = cfg('grab_free')
        del c['tychus']['texts']['L_Site']
        self.assertTrue(any('texts' in e for e in build.validate_tychus(c)))
        c = cfg('grab_free')
        c['tychus']['evac']['site'] = [1]
        self.assertTrue(any('evac.site' in e for e in build.validate_tychus(c)))

    def test_every_text_has_both_languages_and_the_script_stays_ascii(self):
        c = cfg('grab_free')
        for k in build.TY_TEXT_KEYS + build.TY_BUTTON_KEYS:
            self.assertTrue(c['tychus']['texts'][k]['ru'] and c['tychus']['texts'][k]['en'], k)
        ent = build.text_entries(c)
        keys = {k for k, _ in ent['ruRU']}
        for k in build.TY_TEXT_KEYS:
            self.assertIn(build.TY_TEXT_PREFIX + k, keys)
        for k in ('Button/Name/GhostOpsPheromone', 'Button/Tooltip/GhostOpsPheromone', 'Button/Hotkey/GhostOpsPheromone', 'Button/Name/GhostOpsExtract', 'Button/Name/GhostOpsEvacuate',
                  'Behavior/Name/GhostOpsCarrier', 'Unit/Name/GhostOpsPheromone', 'Button/Name/GhostOpsTurretSalvo', 'Button/Name/GhostOpsFold'):
            self.assertIn(k, keys)
        # the numbers of the configuration are put into the tooltips
        tip = dict(ent['ruRU'])['Button/Tooltip/GhostOpsPheromone']
        self.assertIn('15', tip)
        self.assertNotIn('{', tip)
        self.assertTrue(build.build_block(build.apply_ce0(ADAPTER, c), c).isascii())

    def test_the_scene_lines_are_readable_in_the_time_they_get(self):
        import re
        mod = open(os.path.join(ROOT, 'core', 'GhostOpsTychus.galaxy'), encoding='utf-8').read()
        c = cfg('grab_free')
        for ident, sec in re.findall(r'GhostOps_Ty_Line\("(\w+)", "\w+", ([0-9.]+)\)', mod):
            text = c['tychus']['texts']['L_' + ident]['ru']
            self.assertGreaterEqual(float(sec) * 17, len(text), (ident, sec, len(text)))  # about 17 characters a second


class Catalog(unittest.TestCase):
    def setUp(self):
        self.frags = build.catalog_fragments(cfg('grab_free'))

    def test_the_decoy_ability_has_charges_a_visible_shell_and_a_capsule(self):
        a = self.frags['AbilData.xml']
        self.assertIn('<CAbilEffectTarget id="GhostOpsPheromone">', a)
        self.assertIn('<CountMax value="2"/>', a)
        self.assertIn('<TimeUse value="12"/>', a)
        self.assertIn('<Range value="15"/>', a)
        self.assertIn('<Flags index="BestUnit" value="1"/>', a)  # one order to a group of Marauders = one decoy
        e = self.frags['EffectData.xml']
        self.assertIn('PunisherGrenadesLMWeapon', e)
        self.assertIn('<SpawnUnit value="GhostOpsPheromone"/>', e)
        self.assertIn('<AreaArray Radius="7"/>', e)  # the pointer shows the attraction area
        u = self.frags['UnitData.xml']
        self.assertIn('<CUnit id="GhostOpsPheromone"', u)
        self.assertIn('<LifeMax value="450"/>', u)
        # its own look: the egg of the Zerg with a green tint and a cloud, never the fuel container (the barrel data and the canister model are not used)
        a = self.frags['ActorData.xml']
        self.assertIn('<CActorUnit id="GhostOpsPheromone" parent="Egg" unitName="Egg">', a)
        self.assertIn('FungalGrowth', a)
        self.assertNotIn('ExplodingBarrel', u)
        self.assertNotIn('GasCanister', a + u)
        self.assertNotIn('ModelData.xml', self.frags)
        self.assertIn('btn-ability-zerg-sporecloud.dds', self.frags['ButtonData.xml'])
        self.assertIn('<CActorRange id="GhostOpsPheroRange" parent="RangeAbil" abil="GhostOpsPheromone"/>', self.frags['ActorData.xml'])

    def test_the_capsule_belongs_to_nobody_so_the_protoss_never_choose_it(self):
        mod = open(os.path.join(ROOT, 'core', 'GhostOpsTychus.galaxy'), encoding='utf-8').read()
        self.assertIn('UnitSetOwner(lv_u, 0, false);', mod)  # neutral: no alliance between the players is touched
        self.assertNotIn('PlayerSetAlliance', mod)
        self.assertNotIn('SetAlliance', mod)

    def test_the_marauder_the_scv_and_the_transport_get_their_buttons(self):
        u = self.frags['UnitData.xml']
        self.assertIn('<CUnit id="Marauder">', u)
        self.assertIn('AbilCmd="GhostOpsPheromone,Execute" Row="2" Column="1"', u)
        self.assertIn('AbilCmd="GhostOpsExtract,Execute"', u)
        self.assertIn('<CUnit id="Hercules">', u)
        self.assertIn('AbilCmd="GhostOpsEvacuate,Execute"', u)

    def test_kits_cost_nothing_and_the_turret_gets_the_ground_salvo_and_the_fold_command(self):
        u = self.frags['UnitData.xml']
        self.assertEqual(u.count('<CUnit id="MissileTurret">'), 1)  # merged into one entry
        self.assertIn('GhostOpsTurretSalvo', u)
        self.assertIn('GhostOpsFold', u)
        self.assertIn('<CostResource index="Minerals" value="0"/>', u)
        self.assertIn('Build6', self.frags['AbilData.xml'])
        self.assertIn('Build7', self.frags['AbilData.xml'])

    def test_the_prototype_has_none_of_it(self):
        frags = build.catalog_fragments(cfg('prototype'))
        self.assertNotIn('GhostOpsPheromone', ''.join(frags.values()))
        gen = build.gen_tychus(cfg('prototype'))
        self.assertIn('go_tyOn = false;', gen)


class Hooks(unittest.TestCase):
    def test_the_adapter_hooks_replace_the_guardian_race_and_poll_the_result(self):
        a = build.apply_ce0(ADAPTER, cfg('grab_free'))
        calls = ' '.join(h['call'] for h in a['extra_hooks'])
        for fn in ('GhostOps_Ty_TrimMarauders', 'GhostOps_Ty_OnMarauders', 'GhostOps_Ty_GuardPrefer', 'GhostOps_Ty_OnGuardianDied', 'GhostOps_Ty_PollResult', 'GhostOps_Ty_BaseLossOk'):
            self.assertIn(fn, calls)
        self.assertIn('GhostOps_Ty_Bind(gv_artifact', a['start_hooks'][0]['call'])
        self.assertIn('core/GhostOpsTychus.galaxy', a['modules'])
        self.assertIn('core/GhostOpsFold.galaxy', a['modules'])

    @unittest.skipUnless(os.path.isfile(SRC), 'source map not extracted')
    def test_every_anchor_of_the_hooks_exists_in_the_original_script(self):
        script = sc2mpq.Archive(build.read(SRC)).read('MapScript.galaxy').decode('utf-8-sig')
        for h in ADAPTER['extra_hooks']:
            start = script.index('bool %s' % h['function'])
            end = script.index('\nbool ', start + 10) if '\nbool ' in script[start + 10:] else len(script)
            body = script[start:end]
            anchor = h.get('after') or h.get('before')
            self.assertEqual(body.count(anchor), 1, (h['function'], anchor))

    @unittest.skipUnless(os.path.isfile(SRC), 'source map not extracted')
    def test_the_real_map_builds_and_verifies_for_the_free_test_and_the_prototype(self):
        for preset in ('grab_free', 'prototype'):
            ns = argparse.Namespace(mission='ttychus01', preset=preset, diag=False, multiplier=None, source=None)
            self.assertEqual(build.cmd_build(ns), 0, preset)
        arc = sc2mpq.Archive(build.read(os.path.join(ROOT, 'dist', 'GhostOps_TTychus01_grab_free.SC2Map')))
        script = arc.read('MapScript.galaxy').decode('utf-8-sig')
        self.assertIn('GhostOps_Ty_PollResult()', script)
        self.assertEqual(script.count('GhostOps_Ty_Bind(gv_artifact, gv_zergArtifactAttackers, gv_zergSpeedBumpUnits, gv_artifactGuardiansNorth, gv_artifactGuardiansSouth); GhostOps_OnMissionStart();'), 1)


class Card(unittest.TestCase):
    def test_the_free_test_card_says_what_it_is_and_shows_the_composition(self):
        cards = {p['name']: p for p in launcher_core.profiles_of('ttychus01')}
        self.assertEqual(list(cards), ['prototype', 'grab_free'])
        card = cards['grab_free']['card']
        self.assertIn('ничего не списывается', card)
        self.assertIn('12 КСМ', card)
        self.assertIn('3 мародёра', card)
        self.assertNotIn('{', card)
        self.assertEqual(launcher_core.default_profile('ttychus01'), 'grab_free')
        self.assertEqual(launcher_core.mission_info('ttychus01')['title'], 'Хватай и беги')
        self.assertTrue(any('Феромонная приманка' in l for l in launcher_core.detail_lines('ttychus01', 'grab_free')))

    def test_the_free_test_is_not_part_of_the_campaign(self):
        import campaign_flow as cf
        self.assertIsNone(cf.step_of('ttychus01'))
        self.assertNotIn('campaign', cfg('grab_free'))


if __name__ == '__main__':
    unittest.main()
