"""The package after the Owner's playthrough of 2026-10-25 (Evacuation r3, Epidemic r3, Zero Hour r3): configuration, generated data and the guarantees for the earlier versions."""
import copy
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import launcher_core  # noqa: E402

TH1, TH2, TR3 = build.load_adapter('thanson01'), build.load_adapter('thanson02'), build.load_adapter('traynor03')


def cfg(adapter, preset):
    return build.resolve_config(adapter, preset)[0]


def galaxy(name):
    return open(os.path.join(ROOT, 'core', name), 'rb').read().decode('ascii')


class Evacuation(unittest.TestCase):
    def setUp(self):
        self.r3 = cfg(TH1, 'sniper_next_r3')
        self.free = cfg(TH1, 'sniper_next_free_r3')

    def test_valid_and_the_free_test_has_no_campaign(self):
        for c in (self.r3, self.free, cfg(TH1, 'sniper_next_r3_ce0_dev'), cfg(TH1, 'sniper_next_r3_campaign_dev')):
            self.assertEqual(build.validate_config(c), [])
        self.assertIsNone(self.free.get('campaign'))
        self.assertEqual(self.r3['campaign']['operation_id'], 'STANDALONE')

    def test_the_recommendation_the_order_and_the_free_test_are_one_source(self):
        tk = self.r3['hanson']['turret_kits']
        extra = tk['scv']['recommended_total'] - tk['scv']['stock']
        self.assertEqual(tk['order'], {'turret_kits': tk['recommended'], 'scvs': extra})
        self.assertEqual(self.free['hanson']['turret_kits']['order'], tk['order'])
        self.assertIn('go_hExtraScvs = %d;' % extra, build.gen_hanson(self.free))
        card = next(p for p in launcher_core.profiles_of('thanson01') if p['name'] == 'sniper_next_free_r3')['card']
        self.assertIn('КСМ: всего %d (%d штатных + %d дополнительных' % (tk['scv']['recommended_total'], tk['scv']['stock'], extra), card)
        self.assertNotIn('{', card)

    def test_containers_have_no_shared_stock_and_no_array(self):
        ct = self.r3['hanson']['containers']
        self.assertEqual((ct['limit'], ct['gas_cost']), (0, 25))
        old = cfg(TH1, 'sniper_next_r2')
        self.assertEqual(old['hanson']['containers']['limit'], 12)  # the earlier revision keeps its stock
        bad = copy.deepcopy(self.r3)
        bad['hanson']['containers']['gas_cost'] = 0
        self.assertTrue(build.validate_config(bad))  # no stock and no price would be a free infinity
        src = galaxy('GhostOpsHanson.galaxy')
        self.assertNotIn('go_hContN', src)
        self.assertNotIn('go_hCont[', src)
        self.assertNotIn('>= 24', src.split('GhostOps_Hanson_ContCreated')[1].split('GhostOps_Hanson_ContDied')[0])
        self.assertIn('UnitSetCustomValue(lv_u, 0, IntToFixed(TextTagLastCreated()))', src)

    def test_the_story_starts_by_the_event_and_every_line_has_the_reading_time(self):
        st = self.r3['hanson']['story']
        self.assertEqual(st['event'], 'base_handed')
        code = build.gen_hanson(self.r3)
        self.assertIn('go_hStoryEvent = true;', code)
        secs = [float(x) for x in re.findall(r'go_hLnSec\[\d+\] = ([0-9.]+);', code)]
        for ln, sec in zip(self.r3['hanson']['lines'], secs):
            need = max(len(ln['text']['ru']), len(ln['text']['en'])) / float(st['chars_per_second'])
            self.assertGreaterEqual(sec + 0.01, max(need, st['min_seconds']), ln['id'])
        self.assertNotIn('go_hStoryEvent', build.gen_hanson(cfg(TH1, 'sniper_next_r2')))
        adapter_hooks = {(h['function'], h['where']) for h in build.hook_list(TH1)}
        self.assertIn(('gt_SwitchtoEscortPhaseQ_Func', 'after'), adapter_hooks)  # after the original scene of the handover
        self.assertIn(('gt_SwitchtoEscortPhase_Func', 'before'), adapter_hooks)

    def test_the_rifle_shot_data(self):
        frags = build.catalog_fragments(self.r3)
        abil = frags['AbilData.xml']
        self.assertIn('<CAbilEffectTarget id="Snipe">', abil)
        self.assertIn('<Effect index="0" value="GhostOpsShotCast"/>', abil)
        self.assertIn('<Cooldown TimeUse="1.6"/>', abil)
        self.assertNotIn('Biological,Visible;Self,Player,Ally', abil.split('<CAbilEffectTarget id="Snipe">')[1].split('</CAbilEffectTarget>')[0])
        self.assertIn('GhostOpsShotMiss', frags['EffectData.xml'])
        self.assertIn('<Amount value="250"/>', frags['EffectData.xml'])
        self.assertIn('GhostOpsShotMissAttack', frags['ActorData.xml'])
        for frag in frags.values():
            ET.fromstring('<Catalog>' + frag + '</Catalog>')
        old = build.catalog_fragments(cfg(TH1, 'sniper_next_r2'))
        self.assertNotIn('GhostOpsShotCast', ''.join(old.values()))  # the earlier revision keeps the stock Snipe
        ent = dict(build.text_entries(self.r3)['ruRU'])
        self.assertIn('Button/Tooltip/Snipe', ent)
        self.assertNotIn('{', ent['Button/Tooltip/Snipe'])
        bad = copy.deepcopy(self.r3)
        bad['ghost_tuning']['snipe']['rifle_shot']['assist_radius'] = 50
        self.assertTrue(build.validate_config(bad))

    def test_the_shot_module_rules_are_in_the_code(self):
        src = galaxy('GhostOpsHanson.galaxy')
        body = src.split('bool GhostOps_Hanson_ShotExec')[1].split('// The state line of the HUD')[0]
        self.assertIn('lv_far', body)  # a far click is clamped to the range, the Ghost never walks
        self.assertIn('GhostOpsFuelContainer', body)  # a container is hit directly only
        self.assertNotIn('GhostOpsFuelContainer', body.split('lv_c == null')[1])  # the assistance never picks one
        self.assertIn('UnitCreateEffectPoint(lv_g, "GhostOpsShotMiss"', body)
        self.assertNotRegex(body, r'RandomInt|RandomFixed')  # no chance to hit

    def test_the_salvo_and_the_detector_are_part_of_the_revision(self):
        frags = build.catalog_fragments(self.r3)
        self.assertEqual(frags['UnitData.xml'].count('<CUnit id="MissileTurret">'), 1)
        self.assertIn('GhostOpsTurretSalvo', frags['AbilData.xml'])
        dn = cfg(TR3, 'defence_next')['defence']['salvo']
        self.assertEqual({k: self.r3['hanson']['salvo'][k] for k in dn}, dn)  # the numbers of the other missions
        self.assertTrue(self.r3['detector_analysis']['always'])
        block = build.build_block(build.apply_ce0(TH1, self.r3), self.r3)
        self.assertIn('go_daAlways = true;', block)
        r2 = cfg(TH2, 'epidemic_free_r2')
        self.assertIn('go_daAlways = false;', build.build_block(build.apply_ce0(TH2, r2), r2))

    def test_the_kit_messages_are_plain(self):
        t = self.r3['hanson']['texts']
        self.assertIn('Начато строительство турели', t['KitsReservedMsg']['ru'])
        self.assertNotIn('занят', t['KitsReservedMsg']['ru'])

    def test_the_earlier_revisions_are_not_changed(self):
        for name in ('sniper_next', 'sniper_next_r2', 'sniper_next_free_r2'):
            c = cfg(TH1, name)
            self.assertNotIn('rifle_shot', c['ghost_tuning']['snipe'])
            self.assertFalse((c.get('detector_analysis') or {}).get('always'))
            code = build.gen_hanson(c)
            self.assertNotIn('go_hShotOn', code)
            self.assertIn('go_hExtraScvs = 0;', code)


class Epidemic(unittest.TestCase):
    def setUp(self):
        self.c = cfg(TH2, 'epidemic_free_r3')

    def test_valid_and_free(self):
        self.assertEqual(build.validate_config(self.c), [])
        self.assertFalse(self.c.get('campaign'))
        self.assertEqual(build.output_name(TH2, 'epidemic_free_r3'), 'GhostOps_THanson02_epidemic_free_r3.SC2Map')

    def test_the_bunker_kits_and_the_composition(self):
        h = self.c['hanson']
        bk = h['bunker_kits']
        self.assertTrue(bk['enabled'])
        code = build.gen_hanson(self.c)
        self.assertIn('go_hBkOn = true;', code)
        self.assertIn('go_hBkOrdered = %d;' % bk['order']['bunker_kits'], code)
        self.assertIn('go_hExtraScvs = %d;' % h['free_squad']['scvs'], code)
        frags = build.catalog_fragments(self.c)
        self.assertIn('<CUnit id="Bunker">', frags['UnitData.xml'])
        self.assertEqual(frags['UnitData.xml'].count('<CUnit id="MissileTurret">'), 1)
        self.assertEqual(frags['AbilData.xml'].count('<CAbilBuild id="TerranBuild">'), 1)
        self.assertIn('Build7', frags['AbilData.xml'])
        card = next(p for p in launcher_core.profiles_of('thanson02') if p['name'] == 'epidemic_free_r3')['card']
        total = h['free_squad']['marines'] + self.c['epidemic']['stock_marines']
        self.assertIn('морпехи: всего %d (%d штатных и %d добавленных' % (total, self.c['epidemic']['stock_marines'], h['free_squad']['marines']), card)
        self.assertIn('КСМ: всего %d' % (self.c['epidemic']['stock_scvs'] + h['free_squad']['scvs']), card)
        self.assertNotIn('{', card)
        # the ordinary soldiers keep their numbers: no multiplier at all
        self.assertEqual(self.c['base_support']['damage_multiplier'], 1)

    def test_the_earlier_revisions_have_no_bunkers_and_keep_their_detector(self):
        for name in ('epidemic_free', 'epidemic_free_r2'):
            c = cfg(TH2, name)
            self.assertNotIn('bunker_kits', c['hanson'])
            self.assertFalse((c.get('detector_analysis') or {}).get('always'))
        self.assertTrue(self.c['detector_analysis']['always'])
        self.assertEqual(self.c['hanson']['containers']['limit'], 10)  # the limit of the Epidemic is not changed by the Evacuation decision

    def test_kits_are_not_limited_by_the_tracker_array(self):
        src = galaxy('GhostOpsHanson.galaxy')
        scan = src.split('void GhostOps_Hanson_KitScan')[1].split('bool GhostOps_Hanson_KitTick')[0]
        self.assertIn('UnitGetCustomValue(lv_u, 1) < 0.5', scan)  # a finished structure is marked, it needs no place of the tracker


class ZeroHour(unittest.TestCase):
    def setUp(self):
        self.c = cfg(TR3, 'defence_r3')

    def test_valid(self):
        for name in ('defence_r3', 'defence_r3_free', 'defence_r3_dev'):
            self.assertEqual(build.validate_config(cfg(TR3, name)), [], name)
        self.assertIsNone(cfg(TR3, 'defence_r3_free').get('campaign'))

    def test_the_garrison_has_the_ordinary_damage_and_the_salvo_is_unchanged(self):
        t = self.c['tactical']
        self.assertEqual(t['garrison']['damage_multiplier'], 1)
        self.assertEqual(cfg(TR3, 'defence_next')['tactical']['garrison']['damage_multiplier'], 8)  # the version the Owner played
        self.assertEqual(self.c['defence']['salvo'], cfg(TR3, 'defence_next')['defence']['salvo'])
        self.assertEqual(self.c['defence']['waves'], cfg(TR3, 'defence_next')['defence']['waves'])

    def test_grenades_of_both_ghosts_and_the_zerg_buildings(self):
        gr = self.c['tactical']['grenade']
        self.assertEqual((gr['charges'], gr['carriers'], gr['hotkey']), (4, 'both', 'G'))
        frags = build.catalog_fragments(self.c)
        eff = frags['EffectData.xml']
        self.assertIn('GhostOpsAPImpactSet', eff)
        self.assertIn('Ground,Structure,Biological,Visible;', eff)  # the biological structures of the Zerg
        self.assertIn('Ground,Mechanical,Visible;', eff)  # the machines and the other structures stay as in the accepted mission
        bio = eff.split('<CEffectEnumArea id="GhostOpsAPSearchBio">')[1].split('</CEffectEnumArea>')[0]
        self.assertRegex(bio, r'Player,Ally,Neutral,Air,Missile')  # no air, no own, no allies, no missiles
        self.assertNotIn('Fighter', bio)
        old = build.catalog_fragments(cfg(TR3, 'defence_next'))
        self.assertNotIn('GhostOpsAPSearchBio', ''.join(old.values()))
        tac2 = build.catalog_fragments(cfg(build.load_adapter('traynor02'), 'tactical_next'))['EffectData.xml']
        self.assertNotIn('GhostOpsAPSearchBio', tac2)  # the accepted grenade of Outlaws is not touched
        self.assertIn('go_tacGrenBoth = true;', build.gen_tactical(self.c))
        for frag in frags.values():
            ET.fromstring('<Catalog>' + frag + '</Catalog>')

    def test_the_nuclear_strike_and_its_counter(self):
        n = self.c['tactical']['nuke']
        self.assertEqual((n['range'], n['count'], n['both_may_aim']), (48, 2, True))
        nd = n['damage']
        self.assertGreaterEqual(nd['areas'][0][0], 8)  # the full damage reaches the neighbouring Hatcheries of a base (7.8 .. 8.6 apart)
        code = build.gen_tactical(self.c)
        self.assertIn('go_tacStatus = true;', code)
        self.assertIn('go_pnExtra = 2;', build.gen_panel(self.c))
        src = galaxy('GhostOpsTactical.galaxy')
        self.assertIn('go_tacLaunches < go_tacNukeCount', src)  # the counter is the launches, never the clicks
        status = src.split('bool GhostOps_Tac_StatusTick')[1].split('// Death of the spotter')[0]
        self.assertIn('go_tacNukeCount - go_tacLaunches', status)
        ent = dict(build.text_entries(self.c)['ruRU'])
        self.assertEqual(ent[build.TAC_TEXT_PREFIX + 'NukeAmmo'], 'Ядерные ракеты')
        for k, v in ent.items():
            if k.startswith(build.TAC_TEXT_PREFIX) and k.split('_')[-1] in ('ObjectiveText', 'ArrivalText', 'Tip2Text', 'SwannExplain'):
                self.assertNotIn('ракета одна', v)
                self.assertNotIn('одну ядерную', v)

    def test_the_marks_are_persistent_and_the_loop_is_off(self):
        self.assertIn('go_zhMarksPersist = true;', build.gen_zerohour(self.c))
        self.assertIn('go_zhMarksPersist = false;', build.gen_zerohour(cfg(TR3, 'defence_next')))
        src = galaxy('GhostOpsZeroHour.galaxy')
        self.assertIn('!go_zhMarksPersist && ((GameGetMissionTime() - go_zhLastPing)', src)
        self.assertIn('PingDestroy(go_zhPingId[lv_i]);', src)  # the mark of a destroyed target goes away
        dfn = galaxy('GhostOpsDefence.galaxy')
        self.assertIn('go_zhMarksPersist && go_zhMarksShown', dfn)  # a load draws them again, never doubled

    def test_rebel_labels_and_the_hooks(self):
        self.assertTrue(self.c['tactical']['rebel_labels']['enabled'])
        hooks = {h['function'] for h in build.hook_list(TR3)}
        for n in (1, 2, 3):
            self.assertIn('gt_TransmissionRebelMarines0%dRescuedQ_Func' % n, hooks)
        self.assertTrue(self.c['detector_analysis']['always'])

    def test_cards(self):
        cards = {p['name']: p['card'] for p in launcher_core.profiles_of('traynor03')}
        self.assertIn('Свободный тест', cards['defence_r3_free'])
        for name in ('defence_r3', 'defence_r3_free'):
            self.assertNotIn('{', cards[name])
        self.assertIn('Версия 3', cards['defence_r3'])


class Shared(unittest.TestCase):
    def test_salvo_data_of_the_other_missions_is_unchanged_by_the_shared_module(self):
        a = build.salvo_fragments(cfg(TR3, 'defence_next')['defence']['salvo'])
        b = build.defence_fragments(cfg(TR3, 'defence_next')['defence'])
        for k in a:
            self.assertIn(a[k], b[k])

    def test_every_new_galaxy_source_is_ascii(self):
        for name in os.listdir(os.path.join(ROOT, 'core')):
            if name.endswith('.galaxy'):
                galaxy(name)
        for m in ('thanson01', 'thanson02', 'traynor03'):
            for f in os.listdir(os.path.join(ROOT, 'adapters', m)):
                if f.endswith('.galaxy'):
                    open(os.path.join(ROOT, 'adapters', m, f), 'rb').read().decode('ascii')


if __name__ == '__main__':
    unittest.main()
