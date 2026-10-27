"""THanson02 "Outbreak" (Epidemic), free test version: configuration, generated constants, catalog fragments, texts, launcher card, hooks of the original cycle."""
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import json
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402
import launcher_core  # noqa: E402

ADAPTER = build.load_adapter('thanson02')
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'tmp', 'source', 'THanson02.SC2Map')


class Config(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = build.resolve_config(ADAPTER, 'epidemic_free')

    def test_valid_and_free(self):
        self.assertEqual(build.validate_config(self.cfg), [])
        self.assertFalse(self.cfg.get('campaign'))  # a free test never carries a campaign journal: nothing can be offered for crediting
        self.assertEqual(self.cfg['operatives']['squad'], ['Ghost', 'Ghost'])
        self.assertEqual(self.cfg['hanson']['turrets']['list'], [])  # no ready turrets
        self.assertFalse(self.cfg['hanson']['convoy_command'])
        self.assertTrue(self.cfg['hanson']['turret_kits']['enabled'])
        self.assertTrue(self.cfg['hanson']['free_squad']['enabled'])

    def test_ghost_numbers(self):
        gt = self.cfg['ghost_tuning']
        self.assertEqual(gt['ghost_life'], 45)
        self.assertEqual(gt['snipe']['cost'], 0)  # Snipe costs no energy
        self.assertEqual(gt['cloak_net_per_second'], 0)  # the day cloak is free; the night cloak is set by the module from epidemic.night_cloak
        self.assertLess(self.cfg['epidemic']['night_cloak']['net_per_second'], 0)

    def test_generated_constants(self):
        text = build.gen_epidemic(self.cfg)
        e = self.cfg['epidemic']
        self.assertIn('go_eEnabled = true;', text)
        self.assertIn('go_eTank = %.2f;' % e['fuel']['tank'], text)
        self.assertIn('go_eTruckAt = Point(%.4f, %.4f);' % (e['truck']['x'], e['truck']['y']), text)
        self.assertIn('go_eDevDay = 0.0;', text)  # no shortened cycle in a playable build
        self.assertIn('go_eProtType[0] = "%s";' % e['protected']['types'][0], text)
        self.assertTrue(text.isascii())

    def test_dev_cycle_is_development_only(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg['epidemic']['dev_cycle'] = {'day': 120, 'night': 100}
        self.assertTrue(any('dev_cycle' in x for x in build.validate_config(cfg)))
        dev, _ = build.resolve_config(ADAPTER, 'epidemic_free_ce0_dev')
        dev['epidemic']['dev_cycle'] = {'day': 120, 'night': 100}
        self.assertEqual(build.validate_config(dev), [])
        self.assertIn('go_eDevDay = 120.0;', build.gen_epidemic(dev))

    def test_fragments_and_texts(self):
        frag = build.epidemic_fragments(self.cfg['epidemic'])
        self.assertIn('<CUnit id="Hellion">', frag['UnitData.xml'])
        self.assertIn('<CUnit id="TankerTruck">', frag['UnitData.xml'])
        self.assertIn('GhostOpsNoFuel', frag['BehaviorData.xml'])
        frags = build.catalog_fragments(self.cfg)
        self.assertIn('MissileTurret', frags['UnitData.xml'])  # the kits of the Hanson module
        ent = dict(build.text_entries(self.cfg)['ruRU'])
        for k in build.EPI_TEXT_KEYS:
            self.assertIn(build.EPI_TEXT_PREFIX + k, ent)
        self.assertIn('Behavior/Name/GhostOpsNoFuel', ent)

    def test_card_shows_the_mode_and_the_composition(self):
        names = [p['name'] for p in launcher_core.profiles_of('thanson02')]
        self.assertEqual(names, ['epidemic_free', 'epidemic_free_r2', 'epidemic_free_r3', 'epidemic_free_r4', 'epidemic_free_r5', 'epidemic_free_r6'])
        card = next(p for p in launcher_core.profiles_of('thanson02') if p['name'] == 'epidemic_free_r2')
        self.assertIn('Свободный тест', card['card'])
        nm, st = self.cfg['hanson']['free_squad']['marines'], self.cfg['epidemic']['stock_marines']
        # the total and the added reinforcement are told apart
        self.assertIn('всего %d (%d штатных и %d добавленных)' % (nm + st, st, nm), card['card'])
        self.assertIn('Режим «Свободный тест»', launcher_core.detail_lines('thanson02', 'epidemic_free_r2')[0])
        lines = ' '.join(launcher_core.detail_lines('thanson02', 'epidemic_free_r2'))
        self.assertIn('всего %d (%d штатных миссии и %d добавленных тестом)' % (nm + st, st, nm), lines)
        self.assertIn('Наземный залп', lines)
        self.assertIsNotNone(launcher_core.mission_info('thanson02'))
        self.assertNotEqual(build.output_name(ADAPTER, 'epidemic_free_r2'), build.output_name(ADAPTER, 'epidemic_free'))
        self.assertNotEqual(build.output_name(ADAPTER, 'epidemic_free'), build.output_name(build.load_adapter('thanson01'), 'sniper_next_free_r2'))

    def test_the_salvo_is_in_revision_2_only_and_has_the_numbers_of_defence_next(self):
        old, _ = build.resolve_config(ADAPTER, 'epidemic_free')
        self.assertNotIn('salvo', old['epidemic'])
        self.assertNotIn('GhostOpsTurretSalvo', build.catalog_fragments(old)['AbilData.xml'])
        cfg2 = build.resolve_config(ADAPTER, 'epidemic_free_r2')[0]
        sv = cfg2['epidemic']['salvo']
        dn = build.resolve_config(build.load_adapter('traynor03'), 'defence_next')[0]['defence']['salvo']
        self.assertEqual({k: sv[k] for k in dn}, dn)
        frags = build.catalog_fragments(cfg2)
        self.assertEqual(frags['UnitData.xml'].count('<CUnit id="MissileTurret">'), 1)  # merged with the kit data
        self.assertEqual(frags['UnitData.xml'].count('CostResource index="Minerals" value="0"'), 1)
        for needle in ('GhostOpsTurretSalvo', 'GhostOpsSalvoAim', 'GhostOpsSalvoMain'):
            self.assertIn(needle, ''.join(frags.values()))
        self.assertIn('<Cooldown TimeUse="%g"/>' % sv['cooldown'], frags['AbilData.xml'])
        ent = dict(build.text_entries(cfg2)['ruRU'])
        self.assertIn('Button/Tooltip/GhostOpsTurretSalvo', ent)
        self.assertNotIn('{', ent['Button/Tooltip/GhostOpsTurretSalvo'])
        self.assertIn('%g' % sv['damage'], ent['Button/Tooltip/GhostOpsTurretSalvo'])
        self.assertEqual(ent['Button/Hotkey/GhostOpsTurretSalvo'], 'A')

    def test_container_texts_tell_the_real_rule_and_the_numbers_of_the_settings(self):
        ct = self.cfg['hanson']['containers']
        ent = dict(build.text_entries(self.cfg)['ruRU'])
        tip, info = ent['Button/Tooltip/GhostOpsPlaceContainer'], ent[build.HANSON_TEXT_PREFIX + 'ContainerInfo']
        self.assertNotIn('{', tip + info)
        self.assertNotIn('призрака', info)
        self.assertIn('призрак и Snipe не нужны', info)
        base = ct['damage']
        self.assertIn('%g (%g основных и %g дополнительных)' % (base * (1 + ct['structure_bonus']), base, base * ct['structure_bonus']), tip)
        self.assertNotIn('×2', tip)


class Hooks(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(SRC), 'source map not extracted')
    def test_the_original_anchors_exist_once_and_the_build_verifies(self):
        import sc2mpq
        script = sc2mpq.Archive(open(SRC, 'rb').read()).read('MapScript.galaxy').decode('utf-8-sig')
        for h in build.hook_list(ADAPTER):
            fstart = script.find('bool %s' % h['function'])
            self.assertGreaterEqual(fstart, 0, h['function'])
            body = script[fstart:script.find('\n}', fstart)]
            self.assertEqual(body.count(h['anchor']), 1, (h['function'], h['anchor']))
        cfg, _ = build.resolve_config(ADAPTER, 'epidemic_free')
        block = build.build_block(ADAPTER, cfg)
        out = build.patch_script(script, ADAPTER, block)
        self.assertTrue(re.search(r'GhostOps_Epi_OnNight\(gv_night, gv_nIGHT_DURATION\);', out))
        self.assertTrue(re.search(r'GhostOps_Epi_OnDay\(gv_day, gv_dAY_DURATION\);', out))
        self.assertTrue(out.count('GhostOps_Epi_ExtraHellions') >= 2)


class TruckRevision6(unittest.TestCase):
    """Revision 6: the gas truck stands in Area 7 and is taken only by a close approach; the older revisions keep their old settings."""

    def test_truck_in_area_7_and_close_capture_only_in_revision_6(self):
        ad = build.load_adapter('thanson02')
        r6 = build.resolve_config(ad, 'epidemic_free_r6')[0]['epidemic']['truck']
        r5 = build.resolve_config(ad, 'epidemic_free_r5')[0]['epidemic']['truck']
        self.assertEqual((r6['x'], r6['y']), (100.1, 68.4))
        self.assertEqual((r6['capture_radius'], r6['capture_units'], r6['close_capture']), (2.0, 1, True))
        self.assertEqual(r6['defenders']['infested_terran'] + r6['defenders']['civilian'], 0)  # no extra army: the infested objects of the map around stay
        self.assertEqual((r5['x'], r5['y'], r5['capture_radius'], r5['capture_units']), (107.5, 144.5, 8.0, 2))
        self.assertNotIn('close_capture', r5)
        for k in ('fuel_max', 'fuel_start', 'speed', 'life', 'gas_to_fuel', 'base_refill_rate'):
            self.assertEqual(r6[k], r5[k], k)  # fuel, speed unchanged
        gen6 = build.gen_epidemic(build.resolve_config(ad, 'epidemic_free_r6')[0])
        gen5 = build.gen_epidemic(build.resolve_config(ad, 'epidemic_free_r5')[0])
        self.assertIn('go_eCapClose = true;', gen6)
        self.assertIn('go_eCapClose = false;', gen5)

    def test_card_names_the_revision_and_the_two_changes(self):
        cards = {p['name']: p for p in launcher_core.profiles_of('thanson02')}
        c6 = cards['epidemic_free_r6']
        self.assertIn('ревизия 6', c6['label'])
        self.assertIn('Газовоз в Area 7', c6['card'])
        self.assertIn('Захват только при близком подходе', c6['card'])
        self.assertIn('Газовоз в Area 7', ' '.join(c6['details']))
        self.assertEqual(launcher_core.default_profile('thanson02'), 'epidemic_free_r6')
        self.assertIn('прежняя', cards['epidemic_free_r5']['label'])

    def test_close_capture_needs_a_small_radius(self):
        ad = build.load_adapter('thanson02')
        c = build.resolve_config(ad, 'epidemic_free_r6')[0]
        c['epidemic']['truck']['capture_radius'] = 8.0
        self.assertTrue(any('close_capture' in e for e in build.validate_epidemic(c)))

    def test_detection_and_capture_are_separate_in_the_module(self):
        mod = open(os.path.join(ROOT, 'core', 'GhostOpsEpidemic.galaxy'), encoding='utf-8').read()
        self.assertIn('GhostOpsE_MsgTruckSeen', mod)
        self.assertIn('GhostOpsE_MsgTruckCaptured', mod)
        self.assertLess(mod.index('go_eTruckSeen = true;'), mod.index('GhostOpsE_MsgTruckCaptured'))


if __name__ == '__main__':
    unittest.main()
