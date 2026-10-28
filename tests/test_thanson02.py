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
        self.assertEqual(names, ['epidemic_free', 'epidemic_free_r2', 'epidemic_free_r3', 'epidemic_free_r4', 'epidemic_free_r5', 'epidemic_free_r6', 'epidemic_free_r7', 'epidemic_free_r8'])
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


class Revision7(unittest.TestCase):
    """Revision 7: the supply zone of the base (hellions), the barrel drop of the Hercules, the truck of revision 6; the older revisions keep their numbers."""

    def cfg(self, name='epidemic_free_r7'):
        return build.resolve_config(ADAPTER, name)[0]

    @staticmethod
    def inside(poly, x, y):  # the same ray casting as GhostOps_Epi_InZone
        ins, j = False, len(poly) - 1
        for i in range(len(poly)):
            if (poly[i][1] > y) != (poly[j][1] > y) and x < (poly[j][0] - poly[i][0]) * (y - poly[i][1]) / (poly[j][1] - poly[i][1]) + poly[i][0]:
                ins = not ins
            j = i
        return ins

    def test_valid_and_only_revision_7_has_zone_and_barrels(self):
        c7, c6 = self.cfg(), self.cfg('epidemic_free_r6')
        self.assertEqual(build.validate_config(c7), [])
        self.assertTrue(c7['epidemic']['supply']['enabled'])
        self.assertTrue(c7['epidemic']['barrels']['enabled'])
        self.assertNotIn('supply', c6['epidemic'])
        self.assertNotIn('barrels', c6['epidemic'])
        self.assertEqual((c7['epidemic']['truck']['x'], c7['epidemic']['truck']['y']), (100.1, 68.4))  # the truck of revision 6 is kept
        self.assertTrue(c7['epidemic']['truck']['close_capture'])
        for k in ('fuel', 'hellions', 'protected', 'night_cloak', 'transport'):
            self.assertEqual(c7['epidemic'][k], c6['epidemic'][k], k)  # the numbers of the fuel, the waves-side settings and the transport do not move
        self.assertEqual(c7['hanson']['containers'], c6['hanson']['containers'])  # the container (C, 25 gas, blast numbers) is not changed

    def test_the_zone_holds_the_measured_original_base_and_not_the_neighbourhood(self):
        poly = self.cfg()['epidemic']['supply']['polygon']
        base = {'CommandCenter': (73.5, 91.5), 'Barracks1': (68.5, 97.5), 'Barracks2': (76.5, 97.5), 'Refinery': (66.5, 88.5), 'Depot1': (57.0, 106.0), 'Depot2': (55.0, 108.0),
                'Depot3': (59.0, 108.0), 'Depot4': (57.0, 110.0), 'MercCompound': (62.0, 112.0), 'SensorTower': (81.5, 119.5)}  # measured in the game (th2r7_geom)
        for n, (x, y) in base.items():
            self.assertTrue(self.inside(poly, x, y), n)
        for n, (x, y) in {'truck place': (100.1, 68.4), 'west of the base': (44.0, 90.0), 'infested hut': (100.5, 92.5), 'north-west': (45.0, 120.0), 'far north': (75.0, 128.0)}.items():
            self.assertFalse(self.inside(poly, x, y), n)
        # the old circle (73.5, 91.5, r 18) missed the depots, the Merc Compound and the sensor tower: the reason for the polygon
        for x, y in ((57.0, 110.0), (62.0, 112.0), (81.5, 119.5)):
            self.assertGreater(((x - 73.5) ** 2 + (y - 91.5) ** 2) ** 0.5, 18.0)

    def test_generated_constants(self):
        g7 = build.gen_epidemic(self.cfg())
        g6 = build.gen_epidemic(self.cfg('epidemic_free_r6'))
        for s in ('go_eZoneOn = true;', 'go_eZoneN = 4;', 'go_eZoneX[0] = 50.000;', 'go_bdOn = true;', 'go_bdMax = 2;', 'go_bdFall = 1.300;'):
            self.assertIn(s, g7)
        self.assertNotIn('go_eZoneOn', g6)
        self.assertNotIn('go_bdOn', g6)

    def test_barrel_ability_is_data_with_two_charges_the_reused_pointer_and_a_card_button(self):
        f = build.epidemic_fragments(self.cfg()['epidemic'])
        ab = f['AbilData.xml']
        self.assertIn('<CAbilEffectTarget id="GhostOpsDropBarrel">', ab)
        self.assertIn('<CountMax value="2"/>', ab)
        self.assertIn('<CountUse value="1"/>', ab)
        self.assertIn('<Range value="2"/>', ab)
        self.assertIn('<CursorEffect value="GhostOpsContainerArea"/>', ab)  # the pointer circle of the existing container
        self.assertIn('Face="GhostOpsDropBarrel" Type="AbilCmd" AbilCmd="GhostOpsDropBarrel,Execute"', f['UnitData.xml'])
        self.assertIn('<CUnit id="Hercules">', f['UnitData.xml'])
        self.assertIn('GasCanister', f['ModelData.xml'])  # the falling barrel is the model of the container
        # the barrel is a missile: Launch Missile effect, a Ballistic mover with the flight time and a 3D arrival test, a missile actor and an ACTION ACTOR that launches it from the centre of the ship
        self.assertIn('<CEffectLaunchMissile id="GhostOpsBarrelLaunch">', f['EffectData.xml'])
        self.assertIn('<Driver value="Ballistic"/>', f['MoverData.xml'])
        self.assertIn('<FlightTime value="1.3"/>', f['MoverData.xml'])
        self.assertIn('<ArrivalTestType value="3D"/>', f['MoverData.xml'])
        self.assertIn('<RotationActorType value="Upright"/>', f['MoverData.xml'])
        self.assertIn('<Gravity value="4.4379"/>', f['MoverData.xml'])  # 2 h / T^2: a straight fall from the hull height, no hop
        self.assertIn('<LaunchSiteOps Ops="SOpAttachCenter"/>', f['ActorData.xml'])
        self.assertIn('effectLaunch="GhostOpsBarrelLaunch"', f['ActorData.xml'])
        self.assertNotIn('Damage', f['EffectData.xml'].split('GhostOpsBarrelLaunch')[1])  # no second blast in the data: the module makes the existing one when the impact effect is used
        self.assertNotIn('GhostOpsBarrelBomb', json.dumps(f))  # no dummy unit moved by an order
        self.assertNotIn('GhostOpsDropBarrel', json.dumps(build.epidemic_fragments(self.cfg('epidemic_free_r6')['epidemic'])))

    def test_the_drop_reuses_the_container_blast_and_texts_name_the_numbers(self):
        h = open(os.path.join(ROOT, 'core', 'GhostOpsHanson.galaxy'), encoding='utf-8').read()
        e = open(os.path.join(ROOT, 'core', 'GhostOpsEpidemic.galaxy'), encoding='utf-8').read()
        self.assertEqual(h.count('UnitCreateEffectPoint(lp_src, "GhostOpsCBlast", lp_pos);'), 1)
        self.assertIn('GhostOps_Hanson_ContBlast(lv_k, lv_pos);', h)  # the container shot by a Ghost and ...
        self.assertIn('GhostOps_Hanson_ContBlast(lv_src, go_bdPos[lp_i]);', e)  # ... the dropped barrel use the same blast function
        self.assertIn('TriggerAddEventPlayerEffectUsed(go_bdImpTrig, 1, "GhostOpsBarrelImpact");', e)  # the explosion is started by the arrival of the missile (game logic), not by an animation or a timer
        self.assertIn('AbilityCommand("GhostOpsDropBarrel", 0), c_unitAbilStageComplete', e)  # the Execute stage fires when the order starts (measured): only Complete means the barrel was released; a cancelled order spends nothing
        self.assertIn('UnitAbilityReset(go_eShip', e)
        self.assertLess(e.index('go_bdOut = true;'), e.index('GhostOps_Epi_BarrelsRefill(false);'))  # a refill needs the ship to have left the zone first
        ent = dict(build.text_entries(self.cfg())['enUS'])
        self.assertIn('Hotkey [B]', ent['Button/Tooltip/GhostOpsDropBarrel'])
        self.assertIn('2 barrels', ent['Button/Tooltip/GhostOpsDropBarrel'])
        self.assertEqual(ent['Button/Hotkey/GhostOpsDropBarrel'], 'B')

    def test_barrel_settings_are_validated(self):
        c = self.cfg()
        c['epidemic']['barrels']['count'] = 9
        self.assertTrue(any('barrels.count' in x for x in build.validate_epidemic(c)))
        c = self.cfg()
        c['epidemic']['transport']['unit'] = 'Medivac'
        self.assertTrue(any('Hercules' in x for x in build.validate_epidemic(c)))
        c = self.cfg()
        c['epidemic']['supply']['polygon'] = [[1, 1], [2, 2]]
        self.assertTrue(any('polygon' in x for x in build.validate_epidemic(c)))

    def test_slow_fall_profile_is_development_only(self):
        self.assertEqual(self.cfg('epidemic_free_r7_slow_dev')['epidemic']['barrels']['fall_seconds'], 9.0)
        self.assertEqual(self.cfg()['epidemic']['barrels']['fall_seconds'], 1.3)

    def test_the_ghost_panel_is_off_only_in_revision_7(self):
        self.assertFalse(self.cfg()['panel']['enabled'])
        self.assertTrue(self.cfg('epidemic_free_r6')['panel']['enabled'])
        self.assertTrue(self.cfg('epidemic_free_r4')['panel']['enabled'])
        self.assertIn('go_pnEnabled = false;', build.gen_panel(self.cfg()))
        self.assertIn('go_pnEnabled = true;', build.gen_panel(self.cfg('epidemic_free_r6')))
        self.assertTrue(self.cfg()['detector_analysis']['enabled'])  # the detector warnings stay
        self.assertTrue(self.cfg()['operatives'].get('ghost_permanent_cloak') is not None)


class Revision8(unittest.TestCase):
    """Revision 8 = revision 7 with one correction: the barrels are not refilled by the mere start of a new night."""

    def cfg(self, name):
        return build.resolve_config(ADAPTER, name)[0]

    def test_only_the_refill_rule_differs_from_revision_7(self):
        c7, c8 = self.cfg('epidemic_free_r7'), self.cfg('epidemic_free_r8')
        self.assertEqual(build.validate_config(c8), [])
        b7, b8 = dict(c7['epidemic']['barrels']), dict(c8['epidemic']['barrels'])
        self.assertNotIn('refill_on_night', b7)  # the issued revision 7 keeps its settings (its map is protected and is never rebuilt)
        self.assertIs(b8.pop('refill_on_night'), False)
        self.assertEqual(b7, b8)
        for k in ('supply', 'truck', 'fuel', 'transport'):
            self.assertEqual(c7['epidemic'][k], c8['epidemic'][k], k)
        self.assertFalse(c8['panel']['enabled'])

    def test_generated_switch_and_module_guard(self):
        self.assertIn('go_bdNightRefill = false;', build.gen_epidemic(self.cfg('epidemic_free_r8')))
        self.assertIn('go_bdNightRefill = true;', build.gen_epidemic(self.cfg('epidemic_free_r7')))
        e = open(os.path.join(ROOT, 'core', 'GhostOpsEpidemic.galaxy'), encoding='utf-8').read()
        flat = ' '.join(e.split())
        self.assertIn('if (go_bdOn && go_bdNightRefill) { GhostOps_Epi_BarrelsRefill(true); }', flat)  # no refill at the start of a night in revision 8
        self.assertEqual(e.count('GhostOps_Epi_BarrelsRefill(false);'), 1)  # the only other refill is the return to the supply zone

    def test_switch_is_validated(self):
        c = self.cfg('epidemic_free_r8')
        c['epidemic']['barrels']['refill_on_night'] = 'no'
        self.assertTrue(any('refill_on_night' in x for x in build.validate_epidemic(c)))


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
        self.assertEqual(launcher_core.default_profile('thanson02'), 'epidemic_free_r8')  # revision 8 is the current one for the Owner; 7 (issued, protected) and 6 stay as older versions
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
