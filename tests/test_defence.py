"""TRaynor03 "Оборона и диверсии" (preset defence): validation, wave-weakening tail, stubs in the old profile, the new profile separate from the old."""
import copy
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402


def resolved(preset):
    adapter = build.load_adapter('traynor03')
    cfg, _ = build.resolve_config(adapter, preset)
    return adapter, cfg


class DefenceConfig(unittest.TestCase):
    def test_profile_is_valid_and_marked_new_experimental(self):
        adapter, cfg = resolved('defence')
        self.assertEqual(build.validate_config(cfg), [])
        raw = build.load_json(adapter['config'])['presets']['defence']
        self.assertTrue(raw['experimental'])
        self.assertEqual(raw['badge'], 'Новое')
        self.assertEqual(cfg['zerohour']['min']['marines'], 6)
        self.assertEqual(cfg['ghost_tuning']['snipe']['damage'], 45)

    def test_old_profile_is_untouched(self):
        adapter, cfg = resolved('standard')
        self.assertNotIn('defence', cfg)
        a = build.apply_ce0(adapter, cfg)
        text = build.build_block(a, cfg)
        self.assertNotIn('GhostOps_DEF_Log', text)
        self.assertIn('no defence variant in this build', text)
        self.assertEqual(a.get('defence'), None)

    def test_unknown_key_and_bad_numbers_are_errors(self):
        _, cfg = resolved('defence')
        bad = copy.deepcopy(cfg)
        bad['defence']['nonsense'] = 1
        self.assertTrue(build.validate_defence(bad))
        bad = copy.deepcopy(cfg)
        bad['defence']['scenes']['reveal_seconds'] = 99
        self.assertTrue(build.validate_defence(bad))
        bad = copy.deepcopy(cfg)
        bad['defence']['waves']['rounding'] = 'sideways'
        self.assertTrue(build.validate_defence(bad))

    def test_order_below_six_marines_is_refused(self):
        _, cfg = resolved('defence')
        order = copy.deepcopy(cfg['zerohour']['recommended'])
        order['marines'] = 5
        self.assertTrue(build.validate_zerohour(dict(cfg, zerohour=dict(cfg['zerohour'], recommended=order))))


class DefenceBuild(unittest.TestCase):
    def test_block_and_tail_are_generated_and_ascii(self):
        adapter, cfg = resolved('defence')
        a = build.apply_ce0(adapter, cfg)
        self.assertTrue(a['defence'])
        text = build.build_block(a, cfg)
        self.assertTrue(text.isascii())
        hooks = ''.join(h['call'] for h in build.hook_list(a))
        for name in ('AttackWavesRedZergP02', 'AttackWavesTealZergP03', 'AttackWavesPurpleZergP04', 'StartFirstZergWaveSpecial'):
            self.assertIn('GhostOps_DEF_' + name, hooks)
        # the flag is set before the original starts the AI in the intro
        self.assertIn('GhostOps_ApplyDefenceConfig();', hooks)

    def test_wrap_first_arg_scales_only_zerg_owners(self):
        body = 'libNtve_gf_CreateUnitsAtPoint2(4, "Zergling", 0, gv_pLAYER02_ZERG, p, r, g);\nlibNtve_gf_CreateUnitsAtPoint2(2, "Marine", 0, gv_pLAYER01_USER, p, r, g);\n'
        out = build._wrap_first_arg(body, 'libNtve_gf_CreateUnitsAtPoint2(', None, 0)
        self.assertIn('GhostOps_DEF_Scale(2, 4)', out)
        self.assertIn('libNtve_gf_CreateUnitsAtPoint2(2, "Marine"', out)


class AimedSalvo(unittest.TestCase):
    def setUp(self):
        _, self.cfg = resolved('defence_next')
        self.frag = build.defence_fragments(self.cfg['defence'])

    def test_pattern_is_reproducible_and_inside_the_circle(self):
        a = build.salvo_pattern(5, 1.0)
        self.assertEqual(a, build.salvo_pattern(5, 1.0))
        self.assertTrue(all((x * x + y * y) ** 0.5 <= 1.0 + 1e-9 for x, y in a))
        self.assertEqual(build.salvo_pattern(3, 0), [(0.0, 0.0)] * 3)  # spread 0: every missile at the centre (the old behaviour)

    def test_pointer_shows_the_whole_area_and_the_pointer_actors_exist(self):
        sv = self.cfg['defence']['salvo']
        self.assertIn('<AreaArray Radius="%g" Effect="GhostOpsSalvoDamage"/>' % (sv['radius'] + sv['spread']), self.frag['EffectData.xml'])
        self.assertIn('<CursorEffect value="GhostOpsSalvoAim"/>', self.frag['AbilData.xml'])
        for a in ('CActorSplat id="GhostOpsSalvoCursorSplat"', 'CActorModel id="GhostOpsSalvoCursorModel"', 'CActorRange id="GhostOpsSalvoRange"', 'BarrageModel'):
            self.assertIn(a, self.frag['ActorData.xml'])
        self.assertEqual(self.frag['EffectData.xml'].count('PeriodicOffsetArray'), sv['missiles'])
        self.assertNotIn('Reveal', self.frag['EffectData.xml'])  # the pointer / salvo never reveals anything (the Odin's Barrage does)

    def test_hotkey_a_replaces_the_attack_button_of_the_turret_card_only(self):
        self.assertIn('HotkeyAlias value="Attack"', self.frag['ButtonData.xml'])
        self.assertIn('index="3" Face="GhostOpsTurretSalvo"', self.frag['UnitData.xml'])
        self.assertIn('Row="0" Column="4"', self.frag['UnitData.xml'])
        self.assertNotIn('<AbilArray Link="attack"/>', self.frag['UnitData.xml'])  # the stock attack ability (automatic fire) is not removed
        self.assertNotIn('MissileTurret', self.frag['AbilData.xml'])

    def test_old_salvo_config_is_unchanged(self):
        _, old = resolved('defence')
        frag = build.defence_fragments(old['defence'])
        self.assertNotIn('HotkeyAlias', frag['ButtonData.xml'])
        self.assertIn('Row="1" Column="1"', frag['UnitData.xml'])

    def test_validation(self):
        bad = copy.deepcopy(self.cfg)
        bad['defence']['salvo']['hotkey'] = 'ab'
        self.assertTrue(build.validate_defence(bad))
        bad = copy.deepcopy(self.cfg)
        bad['defence']['salvo']['spread'] = 7
        self.assertTrue(build.validate_defence(bad))


if __name__ == '__main__':
    unittest.main()
