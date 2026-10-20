import contextlib
import io
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import ghostops_menu  # noqa: E402

ADAPTER = build.load_adapter('traynor01')


def flatten(d, prefix=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, prefix + k + '.'))
        else:
            out[prefix + k] = json.dumps(v, ensure_ascii=False)
    return out


class Profiles(unittest.TestCase):
    def setUp(self):
        self.easy, self.easy_name = build.resolve_config(ADAPTER, 'easy')
        self.hard, self.hard_name = build.resolve_config(ADAPTER, 'hard')

    def test_profiles_are_valid_and_named(self):
        for cfg in (self.easy, self.hard):
            self.assertEqual(build.validate_config(cfg), [])
        self.assertEqual(self.easy['profile']['message'], 'Ghost Ops — Лёгкий')
        self.assertEqual(self.hard['profile']['message'], 'Ghost Ops — Сложный')
        raw = build.load_json(ADAPTER['config'])
        self.assertEqual(raw['default_preset'], 'easy')
        self.assertEqual(sorted(raw['presets']), ['easy', 'easy_dev', 'extreme', 'hard'])

    def test_easy_keeps_the_current_balance(self):
        e = self.easy
        self.assertEqual(e['operatives']['squad'], ['Ghost', 'Ghost'])
        self.assertEqual(e['army']['fragile_units'], [{'type': 'Marine', 'max_life': 1}, {'type': 'Raynor01', 'max_life': 45}])
        gt = e['ghost_tuning']
        self.assertEqual((gt['energy_start'], gt['energy_max'], gt['regen_per_second']), (100, 100, 20))
        self.assertEqual((gt['cloak_activation_cost'], gt['cloak_net_per_second']), (0, -10))
        self.assertEqual(gt['snipe'], {'cost': 10, 'damage': 45, 'cast_time': 0.3, 'cooldown': 0})
        self.assertEqual(gt['remove_abilities'], ['TacNukeStrike', 'EMP'])
        self.assertEqual(e['difficulty']['expected'], 3)
        self.assertEqual(e['base_support']['damage_multiplier'], 1)

    def test_hard_differs_from_easy_only_by_snipe_cooldown_and_profile_name(self):
        a, b = flatten(self.easy), flatten(self.hard)
        self.assertEqual(sorted(a), sorted(b))
        diff = sorted(k for k in a if a[k] != b[k])
        self.assertEqual(diff, ['ghost_tuning.snipe.cooldown', 'profile.label', 'profile.message', 'profile.message_en', 'profile.name'])
        self.assertEqual(self.hard['ghost_tuning']['snipe']['cooldown'], 5)

    def test_cooldown_data_is_per_unit_inside_the_ability_cost(self):
        def snipe(cfg):
            frag = build.ghost_tuning_fragments(cfg['ghost_tuning'])['AbilData.xml']
            return {e.get('id'): e for e in ET.fromstring('<Catalog>' + frag + '</Catalog>')}['Snipe']
        hard = snipe(self.hard)
        cost = hard.find('Cost')
        self.assertEqual(cost.get('index'), '0')
        cd = cost.find('Cooldown')
        self.assertEqual(float(cd.get('TimeUse')), 5.0)
        self.assertEqual(float(cost.find('Vital').get('value')), 10)  # cost, cast time are not changed by the profile
        self.assertEqual(float(hard.find('CastIntroTime').get('value')), 0.3)
        self.assertIsNone(cd.get('Link'))  # default cooldown of the ability itself ...
        self.assertIsNone(cd.get('Location'))  # ... and the default location is the casting unit (not the player)
        self.assertIsNone(snipe(self.easy).find('Cost').find('Cooldown'))  # easy: no cooldown element at all
        # no home-made timer in the generated script for the cooldown
        core = open(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), encoding='utf-8').read()
        self.assertNotIn('Snipe', core.split('GhostOps_TuningText')[0])  # only the read-out mentions Snipe

    def test_unknown_preset_is_rejected_not_replaced(self):
        with self.assertRaises(build.ConfigError) as cm:
            build.resolve_config(ADAPTER, 'medium')
        self.assertIn('easy, hard', str(cm.exception))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = build.main(['launch', '--mission', 'traynor01', '--preset', 'nonsense', '--print-only'])
        self.assertEqual(rc, 2)
        self.assertIn('unknown preset', buf.getvalue())

    def test_no_profile_means_easy_and_other_missions_have_no_profiles(self):
        cfg, name = build.resolve_config(ADAPTER, None)
        self.assertEqual(name, 'easy')
        self.assertEqual(cfg['ghost_tuning']['snipe']['cooldown'], 0)
        self.assertEqual(build.resolve_config(build.load_adapter('traynor02'), None)[1], 'tactical')
        for m in ('ttychus01',):
            ad = build.load_adapter(m)
            cfg, name = build.resolve_config(ad, None)
            self.assertIsNone(name)
            self.assertNotIn('profile', cfg)
            self.assertNotIn('ghost_tuning', cfg)
            with self.assertRaises(build.ConfigError):
                build.resolve_config(ad, 'easy')  # a profile makes no sense there

    def test_separate_files_and_manifests(self):
        names = {p: build.output_name(ADAPTER, p) for p in ('easy', 'hard')}
        self.assertEqual(names, {'easy': 'GhostOps_TRaynor01_easy.SC2Map', 'hard': 'GhostOps_TRaynor01_hard.SC2Map'})
        keys = {build.key_for(ADAPTER, p) for p in ('easy', 'hard')}
        self.assertEqual(len(keys), 2)
        self.assertEqual(len({build.build_manifest_path(k) for k in keys}), 2)
        self.assertEqual(len({build.install_manifest_path(k) for k in keys}), 2)
        self.assertEqual(len({build.paths(ADAPTER, None, p)[1] for p in ('easy', 'hard')}), 2)
        # missions without profiles keep their file names
        self.assertEqual(build.output_name(build.load_adapter('traynor02'), None), 'GhostOps_TRaynor02.SC2Map')
        self.assertEqual(build.output_name(build.load_adapter('ttychus01'), None), 'GhostOps_TTychus01.SC2Map')

    def test_launch_command_points_to_the_chosen_file(self):
        for p in ('easy', 'hard'):
            cfg, name = build.resolve_config(ADAPTER, p)
            cmd, dest = build.launch_command(ADAPTER, cfg, name)
            self.assertTrue(dest.endswith('GhostOps_TRaynor01_%s.SC2Map' % p))
            self.assertIn(dest, cmd)
            self.assertIn('-difficulty 3', cmd)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(build.main(['launch', '--mission', 'traynor01', '--preset', 'hard', '--print-only']), 0)
        self.assertIn('GhostOps_TRaynor01_hard.SC2Map', buf.getvalue())
        self.assertNotIn('_easy', buf.getvalue())

    def test_script_stays_ascii_and_profile_text_goes_to_the_string_table(self):
        # regression: a Cyrillic literal in MapScript.galaxy was a compile error (hard build showed a black screen)
        for mission, preset in (('traynor01', 'easy'), ('traynor01', 'hard'), ('traynor02', 'tactical'), ('traynor02', 'prototype'),
                                ('traynor02', 'tactical_dev'), ('ttychus01', None)):
            ad = build.load_adapter(mission)
            cfg, _ = build.resolve_config(ad, preset)
            self.assertTrue(build.build_block(ad, cfg).isascii(), (mission, preset))
        g = build.gen_config(self.hard)
        self.assertIn('go_cfgHasProfile = true;', g)
        self.assertIn('go_cfgPresetText = StringExternal("Param/Value/GhostOpsProfile");', g)
        other = build.gen_config(build.resolve_config(build.load_adapter('ttychus01'), None)[0])
        self.assertIn('go_cfgHasProfile = false;', other)
        self.assertNotIn('StringExternal', other)
        self.assertEqual(build.profile_texts(self.easy), {'ruRU': 'Ghost Ops — Лёгкий', 'enUS': 'Ghost Ops - Easy'})
        self.assertEqual(build.profile_texts(self.hard), {'ruRU': 'Ghost Ops — Сложный', 'enUS': 'Ghost Ops - Hard'})
        self.assertEqual(build.profile_texts(build.resolve_config(build.load_adapter('ttychus01'), None)[0]), {})
        self.assertFalse(self.easy['difficulty']['show_message'])  # the detailed catalog read-out is opt-in (--diag)
        diag, _ = build.resolve_config(ADAPTER, 'hard', diag=True)
        self.assertTrue(diag['difficulty']['show_message'])

    def test_string_table_patch_is_reversible_and_careful(self):
        for nl in (chr(13) + chr(10), chr(10)):
            src = 'A=1' + nl + 'B=Привет' + nl
            out = build.patch_strings(src, build.PROFILE_KEY, 'Ghost Ops')
            self.assertEqual(build.unpatch_strings(out), src)
            self.assertIn(build.PROFILE_KEY + '=Ghost Ops', out)
            with self.assertRaises(ValueError):
                build.patch_strings(out, build.PROFILE_KEY, 'x')  # twice
        with self.assertRaises(ValueError):
            build.patch_strings('A=1', build.PROFILE_KEY, 'x')  # no final line break: refuse to guess
        with self.assertRaises(ValueError):
            build.patch_strings('A=1' + chr(10) + build.PROFILE_KEY + '=old' + chr(10), build.PROFILE_KEY, 'x')


class ExtremeProfile(unittest.TestCase):
    def setUp(self):
        self.easy, _ = build.resolve_config(ADAPTER, 'easy')
        self.hard, _ = build.resolve_config(ADAPTER, 'hard')
        self.extreme, self.name = build.resolve_config(ADAPTER, 'extreme')

    def test_extreme_is_valid_and_experimental(self):
        self.assertEqual(self.name, 'extreme')
        self.assertEqual(build.validate_config(self.extreme), [])
        raw = build.load_json(ADAPTER['config'])
        self.assertTrue(raw['presets']['extreme']['experimental'])
        self.assertFalse(raw['presets']['hard'].get('experimental'))
        self.assertEqual(self.extreme['profile']['label'], 'Экстремальный')

    def test_extreme_differs_from_hard_only_by_one_ghost_life_and_cooldown(self):
        h, x = flatten(self.hard), flatten(self.extreme)
        changed = sorted(k for k in set(h) | set(x) if h.get(k) != x.get(k))
        self.assertEqual(changed, ['ghost_tuning.ghost_life', 'ghost_tuning.snipe.cooldown', 'operatives.squad',
                                   'profile.label', 'profile.message', 'profile.message_en', 'profile.name'])
        self.assertEqual(self.extreme['operatives']['squad'], ['Ghost'])
        self.assertEqual(self.extreme['ghost_tuning']['ghost_life'], 45)
        self.assertEqual(self.extreme['ghost_tuning']['snipe']['cooldown'], 10)
        self.assertEqual(self.hard['ghost_tuning']['snipe']['cooldown'], 5)

    def test_easy_and_hard_keep_their_balance(self):
        for cfg, cd in ((self.easy, 0), (self.hard, 5)):
            self.assertNotIn('ghost_life', cfg['ghost_tuning'])  # ghosts keep the standard 100 HP
            self.assertEqual(cfg['ghost_tuning']['snipe']['cooldown'], cd)
            self.assertEqual(build.effective_fragile_units(cfg),
                             [{'type': 'Marine', 'max_life': 1}, {'type': 'Raynor01', 'max_life': 45}])

    def test_ghost_life_is_set_by_the_covered_player_rule_for_our_ghosts_only(self):
        self.assertEqual(build.effective_fragile_units(self.extreme),
                         [{'type': 'Marine', 'max_life': 1}, {'type': 'Raynor01', 'max_life': 45}, {'type': 'Ghost', 'max_life': 45}])
        g = build.gen_config(self.extreme)
        self.assertIn('go_cfgFragileCount = 3;', g)
        self.assertIn('go_cfgFragileType[2] = "Ghost";', g)
        self.assertIn('go_cfgFragileLife[2] = 45.0;', g)
        self.assertNotIn('Medic', g)
        self.assertEqual(self.extreme['operatives']['squad'], ['Ghost'])
        self.assertEqual(self.hard['operatives']['squad'], ['Ghost', 'Ghost'])
        # no catalog override of the Ghost's health (that would also change enemy Ghosts): only energy / abilities
        unit_xml = build.ghost_tuning_fragments(self.extreme['ghost_tuning'])['UnitData.xml']
        self.assertNotIn('Life', unit_xml)
        # other missions never get the rule
        for m, preset in (('traynor02', 'prototype'), ('ttychus01', None)):
            cfg, _ = build.resolve_config(build.load_adapter(m), preset)
            self.assertEqual(build.effective_fragile_units(cfg), [])

    def test_three_profiles_have_three_separate_files(self):
        names = {p: build.output_name(ADAPTER, p) for p in ('easy', 'hard', 'extreme')}
        self.assertEqual(len(set(names.values())), 3)
        self.assertEqual(names['extreme'], 'GhostOps_TRaynor01_extreme.SC2Map')
        self.assertEqual(len({build.install_manifest_path(build.key_for(ADAPTER, p)) for p in names}), 3)
        self.assertEqual(len({build.build_manifest_path(build.key_for(ADAPTER, p)) for p in names}), 3)

    def test_ghost_life_validation(self):
        for bad in (0, -5, 2000, 'x', True):
            c = json.loads(json.dumps(self.extreme))
            c['ghost_tuning']['ghost_life'] = bad
            self.assertTrue(build.validate_config(c), bad)


class Menu(unittest.TestCase):
    def feed(self, *answers):
        it = iter(answers)

        def fn(prompt=''):
            try:
                return next(it)
            except StopIteration:
                raise EOFError
        return fn

    def test_choices(self):
        out = []
        self.assertEqual(ghostops_menu.choose(self.feed('1'), out.append), 'easy')
        self.assertEqual(ghostops_menu.choose(self.feed('2'), out.append), 'hard')
        self.assertIn('Лёгкий', '\n'.join(out))
        self.assertEqual(ghostops_menu.choose(self.feed('3'), out.append), 'extreme')
        self.assertIn('Экстремальный', chr(10).join(out))
        self.assertIn('Отмена', '\n'.join(out))

    def test_cancel_and_invalid_input_start_nothing(self):
        calls = []
        for answers in (('0',), ('',), ()):
            rc = ghostops_menu.run(self.feed(*answers), lambda *_: None, calls.append)
            self.assertEqual(rc, 0)
        self.assertEqual(calls, [])  # cancel never reaches the launcher
        out = []
        calls = []
        ghostops_menu.run(self.feed('7', 'x', '2'), out.append, calls.append)
        self.assertEqual(calls, ['hard'])  # invalid answers are asked again, never guessed
        self.assertTrue(any('Неверный выбор' in line for line in out))

    def test_menu_launches_the_chosen_profile_through_the_same_launcher(self):
        calls = []
        ghostops_menu.run(self.feed('1'), lambda *_: None, lambda p: calls.append(p) or 0)
        self.assertEqual(calls, ['easy'])

    def test_double_click_file_is_ascii_crlf(self):
        data = open(os.path.join(ROOT, 'GhostOps_TRaynor01.cmd'), 'rb').read()
        self.assertTrue(all(b < 128 for b in data))
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertIn(b'ghostops_menu.py', data)


if __name__ == '__main__':
    unittest.main()
