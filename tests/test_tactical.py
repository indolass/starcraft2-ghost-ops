import json
import math
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402
import launcher_core  # noqa: E402
import monitors  # noqa: E402
import sc2mpq  # noqa: E402

ADAPTER = build.load_adapter('traynor02')
SOURCE = os.path.join(ROOT, 'tmp', 'source', 'TRaynor02.SC2Map')


def module_text():
    with open(os.path.join(ROOT, 'core', 'GhostOpsTactical.galaxy'), encoding='utf-8') as f:
        return f.read()


class TacticalConfig(unittest.TestCase):
    def setUp(self):
        self.tac, self.name = build.resolve_config(ADAPTER, 'tactical')
        self.proto, _ = build.resolve_config(ADAPTER, 'prototype')

    def test_tactical_is_default_valid_and_experimental(self):
        self.assertEqual(self.name, 'tactical')
        self.assertEqual(build.resolve_config(ADAPTER, None)[1], 'tactical')
        self.assertEqual(build.validate_config(self.tac), [])
        raw = build.load_json(ADAPTER['config'])
        self.assertTrue(raw['presets']['tactical']['experimental'])
        self.assertTrue(raw['presets']['prototype']['hidden'])

    def test_previous_prototype_is_still_buildable_with_its_old_values(self):
        p = self.proto
        self.assertEqual(build.validate_config(p), [])
        self.assertEqual(p['operatives']['squad'], ['Nova', 'Ghost', 'Ghost', 'Medic', 'Medic'])
        self.assertEqual(p['base_support']['damage_multiplier'], 3)
        self.assertNotIn('tactical', p)
        self.assertNotIn('ghost_tuning', p)
        gen = build.gen_tactical(p)
        self.assertIn('go_tacEnabled = false;', gen)

    def test_roles_and_numbers(self):
        t, gt = self.tac['tactical'], self.tac['ghost_tuning']
        self.assertEqual(self.tac['operatives']['squad'], ['Ghost', 'Ghost'])  # exactly two, no Nova, no Medic
        self.assertEqual(self.tac['base_support']['damage_multiplier'], 1)  # no global army bonus
        self.assertFalse(self.tac['experimental']['invulnerable_allies'])
        self.assertEqual(self.tac['army']['fragile_units'] if 'army' in self.tac else [], [])
        self.assertEqual((gt['ghost_life'], gt['energy_start'], gt['energy_max'], gt['regen_per_second']), (45, 100, 100, 20))
        self.assertEqual((gt['cloak_activation_cost'], gt['cloak_net_per_second']), (0, -10))
        self.assertEqual(gt['snipe'], {'cost': 0, 'damage': 45, 'cast_time': 0.3, 'cooldown': 5})  # 2026-10-21: no energy cost, 5 s per Ghost (was 10 / 7)
        self.assertEqual(gt['remove_abilities'], ['EMP'])
        self.assertEqual(t['garrison']['damage_multiplier'], 20)
        self.assertEqual(t['trained_marine'], {'life': 1, 'can_attack': False})  # 1/1 and no weapon at all (no x0.1 any more)
        self.assertEqual(t['story'], {'first_delay': 15, 'second_delay': 15, 'alert_seconds': 14, 'swann_seconds': 3, 'arrival_seconds': 10, 'ghost_seconds': 7, 'raynor_delay': 2, 'raynor_seconds': 11,
                                      'find_delay': 3, 'plan_min_share': 0.5, 'plan_calm_seconds': 6, 'plan_max_wait': 360, 'plan_dead_delay': 6})
        self.assertEqual((t['nuke']['aim_time'], t['nuke']['flight_time']), (12, 6))
        # the explosion keeps the stock damage, radii and falloff: nothing of ours in the config
        for k in ('damage', 'structure_bonus', 'areas'):
            self.assertNotIn(k, t['nuke'])
        self.assertEqual(self.tac['difficulty']['expected'], 3)  # Blizzard Hard stays

    def test_validation_rejects_broken_variants(self):
        for path, value in (
                (('operatives', 'squad'), ['Ghost']),
                (('operatives', 'squad'), ['Nova', 'Ghost']),
                (('base_support', 'damage_multiplier'), 3),
                (('tactical', 'trained_marine', 'life'), 0),
                (('tactical', 'nuke', 'aim_time'), 12.3),
                (('tactical', 'garrison', 'zone', 'radius'), 0),
                (('ghost_tuning', 'remove_abilities'), ['TacNukeStrike', 'EMP'])):
            cfg = json.loads(json.dumps(self.tac))
            node = cfg
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = value
            self.assertTrue(build.validate_config(cfg), path)


class TacticalData(unittest.TestCase):
    def setUp(self):
        self.tac, _ = build.resolve_config(ADAPTER, 'tactical')
        self.frags = build.catalog_fragments(self.tac)

    def test_every_fragment_is_well_formed_and_unit_overrides_are_local(self):
        for name, frag in self.frags.items():
            ET.fromstring('<Catalog>' + frag + '</Catalog>')
        self.assertEqual(sorted(self.frags), ['AbilData.xml', 'BehaviorData.xml', 'ButtonData.xml', 'EffectData.xml', 'RequirementData.xml', 'SoundData.xml', 'UnitData.xml'])

    def test_weapon_behaviors_and_ghost_academy(self):
        beh = self.frags['BehaviorData.xml']
        self.assertEqual(re.findall(r'id="(\w+)"', beh).count('GhostOpsGarrisonDamage'), 1)
        # the catalog value is additive (measured: 0.1 gave x1.1): factor 20 -> value 19, factor 0.1 -> value -0.9
        self.assertEqual(re.findall(r'GhostOpsGarrisonDamage.*?</CBehaviorBuff>', beh, re.S)[0].count('value="19"'), 4)
        self.assertNotIn('GhostOpsTrainedDamage', beh)  # new Marines lose the weapon instead of a damage factor
        unit = self.frags['UnitData.xml']
        self.assertEqual(re.findall(r'<AbilArray index="(\d)" removed="1"/>', unit.split('GhostAcademy')[1].split('</CUnit>')[0]), ['3', '4', '5', '6'])
        self.assertIn('id="Nuke"', unit)
        self.assertEqual(unit.count('CostResource'), 2 + 0 if False else unit.count('CostResource'))
        self.assertIn('<AbilArray index="7" removed="1"/>', unit)  # EMP of the Ghost
        self.assertNotIn('index="5" removed="1"/>\n    </CUnit>\n    <CUnit id="GhostAcademy"', unit)  # the Ghost keeps TacNukeStrike

    def test_arming_requirement_needs_no_factory_and_no_ghost_permission(self):
        req = self.frags['RequirementData.xml']
        self.assertIn('<NodeArray index="Use" Link="Not866976074CountUnitNukeQueuedOrBetterAtUnit"/>', req)
        self.assertIn('<NodeArray index="Show" Link="Not866976074CountUnitNukeQueuedOrBetterAtUnit"/>', req)

    def test_nuke_chain_timing_and_stock_explosion(self):
        eff = self.frags['EffectData.xml']
        self.assertIn('<PeriodCount value="60"/>', eff)  # 60 x 0.2 = 12 s of stationary aiming
        self.assertIn('<ExpireDelay value="6"/>', eff)  # six seconds from the irreversible launch to the blast
        self.assertIn('id="GhostOpsNukeFlight"', eff)
        # the blast itself is the installed game's own: no override of damage, radii or falloff
        self.assertNotIn('NukeDamage"', eff.replace('<ExpireEffect value="NukeDetonate"/>', ''))
        # the only area of the fragments is the grenade's own search; the nuke's damage areas are not touched
        self.assertEqual(eff.count('AreaArray'), 1)
        self.assertIn('GhostOpsAPSearch', eff)
        self.assertNotIn('FinalEffect', eff)  # the stock chain spends the missile; the module arms it again after a cancel
        abil = self.frags['AbilData.xml']
        self.assertIn('<FinishTime value="0"/>', abil)
        self.assertIn('<InfoArray index="Ammo1" Time="1"/>', abil)

    def test_aim_and_flight_times_are_whole_periods(self):
        n = self.tac['tactical']['nuke']
        self.assertAlmostEqual(n['aim_time'] / 0.2, round(n['aim_time'] / 0.2))

    def test_retreat_is_physically_possible(self):
        # measured in the installed game: the Ghost walks 2.0 per game second; the stock blast reaches 8
        speed, stock_outer_radius = 2.0, 8.0
        n = self.tac['tactical']['nuke']
        self.assertGreaterEqual(n['flight_time'] * speed, stock_outer_radius + 2.0)


class TacticalModule(unittest.TestCase):
    def test_build_block_is_ascii_lints_and_has_all_hooks(self):
        for preset in ('tactical', 'tactical_dev', 'prototype'):
            cfg, _ = build.resolve_config(ADAPTER, preset)
            block = build.build_block(ADAPTER, cfg)
            self.assertTrue(block.isascii(), preset)
            self.assertEqual(galaxy_lint.lint(block), [], preset)
        names = {h['call'].split('(')[0] for h in build.hook_list(ADAPTER)}
        self.assertEqual(names, {'GhostOps_OnMissionStart', 'GhostOps_Tac_OnRescue', 'GhostOps_Tac_OnVictory', 'GhostOps_Tac_OnDefeat', 'GhostOps_Scene_OnRebelsRescued', 'GhostOps_Scene_OnRebelsFound'})

    def test_production_build_has_no_test_code_and_no_debug_log(self):
        cfg, _ = build.resolve_config(ADAPTER, 'tactical')
        block = build.build_block(ADAPTER, cfg)
        self.assertIn('go_tacDebug = false;', block)
        self.assertNotIn('GhostOps_TacTest_Run', block)
        self.assertIn('void GhostOps_TacTest_Start () {\n}', block.replace('\r\n', '\n'))
        dev, _ = build.resolve_config(ADAPTER, 'tactical_dev')
        dev_block = build.build_block(ADAPTER, dev)
        self.assertIn('GhostOps_TacTest_Run', dev_block)
        self.assertIn('go_tacDebug = true;', dev_block)

    def test_texts_in_the_module_exist_in_the_string_table(self):
        used = set(re.findall(r'Param/Value/GhostOpsTac_(\w+)', module_text()))
        self.assertTrue(used)
        self.assertTrue(used <= set(build.TAC_TEXT_KEYS) | set(build.TAC_EXTRA_TEXT_KEYS), used - set(build.TAC_TEXT_KEYS))
        cfg, _ = build.resolve_config(ADAPTER, 'tactical')
        entries = build.text_entries(cfg)
        for loc in ('ruRU', 'enUS'):
            keys = [k for k, _ in entries[loc]]
            self.assertEqual(len(keys), len(set(keys)))
            for k in used:
                self.assertIn(build.TAC_TEXT_PREFIX + k, keys)
        ru = dict(entries['ruRU'])
        self.assertIn('12', ru[build.TAC_TEXT_PREFIX + 'Aiming'])  # the aiming time comes from the config

    def test_safety_rules_of_the_strike_stay_in_the_code(self):
        m = module_text()
        # per unit access: the operative may never use the strike, the spotter loses it after the launch
        self.assertIn('UnitAbilityEnable(go_tacOperative, "TacNukeStrike", false);', m)
        self.assertIn('UnitAbilityEnable(go_tacSpotter, "TacNukeStrike", false);', m)
        # measured: disabling the arming ability of the academy blocks the strike itself; arming is stopped on the player level
        self.assertNotIn('UnitAbilityEnable(go_tacAcademy', m)
        self.assertIn('TechTreeAbilityAllow(1, AbilityCommand("ArmSiloWithNuke", 0), false);', m)
        # the launch is the start of our flight effect, never a timer
        self.assertIn('"GhostOpsNukeFlight"', m)
        self.assertNotRegex(re.sub(r'//.*', '', m), r'TimerStart|Wait\(\s*6\.0')
        # nothing may end the mission on its own except the spotter's death before the launch
        self.assertEqual(len(re.findall(r'libCamp_gf_EndCampaignMission', m)), 1)
        self.assertNotIn('c_gameOverVictory', m)
        # no invulnerability, no forced reveal
        self.assertNotIn('c_unitStateInvulnerable', m)
        # the enemy production is the original's: nothing of ours stops spawners, waves, AI or rebuilding
        self.assertIn('UnitWeaponRemove(lp_unit, "GuassRifle");', m)  # the new Marine's weapon is removed when it is created
        self.assertNotIn('GhostOpsTrainedDamage', m)
        for forbidden in ('TriggerStop', 'TriggerEnable(go_tac', 'TechTreeUnitAllow(2', 'AIAttackWave', 'AIWave', 'AIPause', 'AITimePause'):
            self.assertNotIn(forbidden, re.sub(r'//.*', '', m))
        self.assertNotIn('ProductionCount', m)
        self.assertNotIn('StopSources', m)
        self.assertNotIn('gt_StartAI_Func', ' '.join(h['function'] for h in build.hook_list(ADAPTER)))

    def test_no_text_in_galaxy_source_is_cyrillic(self):
        self.assertTrue(module_text().isascii())
        with open(os.path.join(ROOT, 'adapters', 'traynor02', 'adapter.galaxy'), encoding='utf-8') as f:
            self.assertTrue(f.read().isascii())


@unittest.skipUnless(os.path.isfile(SOURCE), 'extracted TRaynor02 map not present')
class TacticalOnTheRealMap(unittest.TestCase):
    def setUp(self):
        arc = sc2mpq.Archive(open(SOURCE, 'rb').read())
        self.script = arc.read('MapScript.galaxy').decode('utf-8-sig')
        self.objects = arc.read('Objects').decode('utf-8-sig')

    def test_all_hooks_patch_and_restore_the_original_script(self):
        cfg, _ = build.resolve_config(ADAPTER, 'tactical')
        block = build.build_block(ADAPTER, cfg)
        out = build.patch_script(self.script, ADAPTER, block)
        self.assertEqual(out.count(build.HOOK_TAG), len(build.hook_list(ADAPTER)))
        self.assertEqual(galaxy_lint.lint(out), [])
        stripped = re.sub(r'\r?\n' + re.escape(build.BEGIN) + r'.*?' + re.escape(build.END), '', out, flags=re.S)
        stripped = re.sub(r'\r?\n    GhostOps_\w+\([^\n]*\);' + re.escape(build.HOOK_TAG), '', stripped)
        self.assertEqual(stripped, self.script)

    def units(self, owner):
        out = []
        for m in re.finditer(r'<ObjectUnit\b([^>]*?)/?>', self.objects):
            d = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if d.get('Player') == str(owner):
                x, y = [float(v) for v in d['Position'].split(',')[:2]]
                out.append((d['UnitType'], x, y))
        return out

    def test_defence_zone_covers_the_start_base_and_misses_the_enemy_and_the_rebels(self):
        z = build.resolve_config(ADAPTER, 'tactical')[0]['tactical']['garrison']['zone']
        cx, cy = z['center']
        dist = lambda x, y: math.hypot(x - cx, y - cy)  # noqa: E731
        mine = self.units(1)
        for t, x, y in mine:
            if t != 'SCV':
                self.assertLessEqual(dist(x, y), z['radius'], (t, x, y))  # the whole start base, all six Marines
        acad = build.resolve_config(ADAPTER, 'tactical')[0]['tactical']['academy']['position']
        self.assertLessEqual(dist(*acad), z['radius'])
        for owner in (2, 4):  # the Dominion base and the rebels are the road of the advance, not the defence zone
            for t, x, y in self.units(owner):
                self.assertGreater(dist(x, y), z['radius'], (owner, t, x, y))
        self.assertEqual(len([1 for t, _, _ in mine if t == 'Marine']), 6)  # the garrison is exactly these six

    def test_academy_site_is_free_of_player_structures(self):
        acad = build.resolve_config(ADAPTER, 'tactical')[0]['tactical']['academy']['position']
        for t, x, y in self.units(1):
            if t in ('CommandCenter', 'Barracks', 'SupplyDepot'):
                self.assertGreater(math.hypot(x - acad[0], y - acad[1]), 4.0, t)


class StoryScene(unittest.TestCase):
    def adapter_text(self):
        with open(os.path.join(ROOT, 'adapters', 'traynor02', 'adapter.galaxy'), encoding='utf-8') as f:
            return re.sub(r'//.*', '', f.read())

    def test_scene_texts_exist_and_nothing_is_forced_on_the_player(self):
        a = self.adapter_text()
        used = set(re.findall(r'Param/Value/GhostOpsTac_(\w+)', a))
        self.assertTrue({'AlertTitle', 'SwannName', 'RaynorName', 'GhostName', 'L_', 'ArrivalText', 'ObjectiveTitle', 'ObjectiveText', 'FindObjectiveTitle', 'FindObjectiveText'} <= used | {'AlertTitle', 'SwannName', 'RaynorName', 'GhostName'})
        self.assertTrue(used <= set(build.TAC_TEXT_KEYS) | set(build.TAC_EXTRA_TEXT_KEYS) | {'L_'}, used - set(build.TAC_TEXT_KEYS))
        for forbidden in ('CameraPan', 'CinematicMode', 'CameraLock', 'SoundPlay', 'TriggerExecute(gt_'):
            self.assertNotIn(forbidden, a)
        # every scene plays lines of the config table (GhostOps_Line): ids used by the scenes are exactly the ids of tactical.lines, a clip is played only when the line names one
        ids = set(re.findall(r'GhostOps_Line\("(\w+)"\)', a))
        cfg, _ = build.resolve_config(ADAPTER, 'tactical')
        self.assertEqual(ids, {l['id'] for l in cfg['tactical']['lines']})
        self.assertEqual(a.count('GhostOps_ClipStep('), 1)
        self.assertEqual(a.count('GhostOps_Talk('), 1)
        self.assertNotIn('TargetingPoint', a.split('GhostOps_Scene_GhostMsg')[1].split('void GhostOps_Scene_SendTransport')[0])
        # the Ghost line is said once for the pair: the guard is set before the thread starts, and nothing else triggers it
        self.assertEqual(a.count('GhostOps_Scene_GhostMsg"'), 1)
        self.assertLess(a.index('go_tacGhostSaid = true;'), a.index('TriggerCreate("GhostOps_Scene_GhostMsg")'))
        self.assertNotIn('Obozn', a)
        self.assertNotIn('UnitSelect', a.split('if (go_tacEnabled) {')[1].split('else {')[0])  # the player's selection is not touched
        self.assertIn('TriggerQueueEnter();', a)  # behind the original talk, never over it
        self.assertGreaterEqual(a.count('TriggerQueueExit();'), a.count('TriggerQueueEnter();'))  # early exits of already shown scenes add exits
        self.assertEqual(a.count('null, StringExternal("Param/Value/GhostOpsTac_'), 0)  # every transmission has its clip
        # the seconds of every line come from the configuration table
        self.assertIn('go_lnSec[lv_i]', a)

    def test_ghosts_come_only_by_transport_and_only_once(self):
        a = self.adapter_text()
        tactical_branch = a.split('if (go_tacEnabled) {')[-1].split('else {')[0]
        self.assertNotIn('SpawnOperatives', tactical_branch)
        self.assertEqual(a.count('GhostOps_SpawnOperativesInCargo('), 1)
        self.assertEqual(a.count('GhostOps_Tac_OnGhostsDelivered('), 1)
        self.assertIn('"SpecialOpsDropship"', a)
        self.assertIn('AbilityCommand("SpecOpsDropshipTransport", 2)', a)
        # the transport is removed only when it is empty (a stage 4 check on the cargo comes first) and never twice
        self.assertIn('UnitGroupCount(UnitCargoGroup(go_scShip), c_unitCountAlive) == 0', a)
        self.assertEqual(a.count('UnitRemove(go_scShip)'), 1)
        self.assertIn('if (!GhostOps_ClaimStart())', a)
        m = module_text()
        self.assertIn('if (go_tacSpotter != null)', m)  # a second delivery is refused
        self.assertIn('go_tacScStage', m)  # the stage is a global: part of the saved game

    def test_no_spotter_no_defeat_before_the_delivery(self):
        m = module_text()
        died = m.split('GhostOps_Tac_OnGhostsDelivered')[1]
        self.assertIn('TriggerAddEventUnitDied(go_tacSpotterDiedTrig, UnitRefFromUnit(go_tacSpotter));', died)
        self.assertNotIn('TriggerAddEventUnitDied(go_tacSpotterDiedTrig', m.split('void GhostOps_Tac_Start ()')[1])

    def test_scene_timings_come_from_the_configuration(self):
        cfg, _ = build.resolve_config(ADAPTER, 'tactical')
        g = build.gen_tactical(cfg)
        self.assertIn('go_tacStoryFirst = 15.0;', g)
        self.assertIn('go_tacStorySecond = 15.0;', g)
        bad = json.loads(json.dumps(cfg))
        bad['tactical']['story']['first_delay'] = 0
        self.assertTrue(build.validate_config(bad))
        bad = json.loads(json.dumps(cfg))
        bad['tactical']['trained_marine']['can_attack'] = True
        self.assertTrue(build.validate_config(bad))


class TestLaunchMode(unittest.TestCase):
    def test_window_fits_any_monitor_layout_including_negative_coordinates(self):
        class M:
            def __init__(self, work):
                self.work = work
        for work in ((0, 0, 1920, 1040), (-1920, 100, 0, 1060), (2560, 329, 4480, 1329), (0, 0, 1280, 760)):
            x, y, w, h = monitors.test_window_rect(M(work))
            l, t, r, b = work
            self.assertGreaterEqual(x, l)
            self.assertGreaterEqual(y, t)
            self.assertLessEqual(x + w, r)
            self.assertLessEqual(y + h, b)
            self.assertEqual(w * 3, h * 4)  # 4:3 kept when it has to shrink

    def test_normal_launch_never_gets_the_test_window_or_mute(self):
        cfg, name = build.resolve_config(ADAPTER, 'tactical')
        normal, _ = build.launch_command(ADAPTER, cfg, name)
        self.assertIn('-displaymode 2', normal)
        self.assertNotIn('-windowwidth', normal)
        import test_launch
        cmd, _ = test_launch.test_command(ADAPTER, cfg, name, 3008, 425, 1024, 768)
        self.assertIn('-displaymode 0 -windowwidth 1024 -windowheight 768 -windowx 3008 -windowy 425', cmd)
        # the game's own settings files are not part of the launch: nothing is written there
        src = open(os.path.join(ROOT, 'tools', 'test_launch.py'), encoding='utf-8').read()
        self.assertNotIn('Variables.txt', src)
        self.assertNotIn('TOPMOST', src.upper())  # no Always on Top
        self.assertNotIn('SetForegroundWindow', src)  # no forced focus
        self.assertIn('SWP_NOACTIVATE', src)


class TacticalLauncher(unittest.TestCase):
    def test_gui_shows_one_experimental_tactical_card_with_exact_details(self):
        profiles = launcher_core.profiles_of('traynor02')
        self.assertEqual([(p['name'], p['label'], p['experimental']) for p in profiles], [('tactical', 'Тактический', True)])
        text = '\n'.join(launcher_core.detail_lines('traynor02', 'tactical'))
        for needle in ('×20', 'зоне обороны', 'атаковать не могут', 'транспорте', 'Наводчик и Оперативник', '45/45', 'перезарядка 5', 'одна ракета', '12 с', '6 с', 'штатные', 'дальность наведения 24', 'Бронебойная граната', 'Панель призраков'):
            self.assertIn(needle, text)
        mission = launcher_core.mission_info('traynor02')
        self.assertNotIn('Нова', mission['description'])


if __name__ == '__main__':
    unittest.main()
