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
        card = next(p for p in launcher_core.profiles_of('thanson02') if p['name'] == 'epidemic_free')
        self.assertIn('Свободный тест', card['card'])
        self.assertIn('%d морпехов' % self.cfg['hanson']['free_squad']['marines'], card['card'])
        self.assertEqual([p['name'] for p in launcher_core.profiles_of('thanson02')], ['epidemic_free'])
        self.assertIn('Режим «Свободный тест»', launcher_core.detail_lines('thanson02', 'epidemic_free')[0])
        self.assertIsNotNone(launcher_core.mission_info('thanson02'))
        self.assertNotEqual(build.output_name(ADAPTER, 'epidemic_free'), build.output_name(build.load_adapter('thanson01'), 'sniper_next_free_r2'))


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


if __name__ == '__main__':
    unittest.main()
