"""TRaynor02 version 2 (preset tactical_next): the options are config driven, the old profiles keep their values, the new code is inert without the options."""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import galaxy_lint  # noqa: E402

ADAPTER = build.load_adapter('traynor02')
NEXT, _ = build.resolve_config(ADAPTER, 'tactical_next')
OLD, _ = build.resolve_config(ADAPTER, 'tactical')


def clone(cfg):
    return json.loads(json.dumps(cfg))


class NextConfig(unittest.TestCase):
    def test_valid_and_the_old_profile_is_untouched(self):
        self.assertEqual(build.validate_config(NEXT), [])
        t = NEXT['tactical']
        self.assertEqual(t['nuke']['range'], 48)  # twice the 24 of the first build
        self.assertEqual(OLD['tactical']['nuke']['range'], 24)
        self.assertNotIn('damage', OLD['tactical']['nuke'])  # the stock damage of the old profile
        self.assertNotIn('victory', OLD['tactical'])
        self.assertEqual(t['grenade']['charges'], 2)
        self.assertEqual(t['grenade']['hotkey'], 'G')
        self.assertEqual(OLD['tactical']['grenade'].get('hotkey'), None)

    def test_output_map_is_a_new_file(self):
        raw = build.load_json(ADAPTER['config'])
        self.assertFalse(raw['presets']['tactical_next'].get('hidden'))  # a launcher card of its own
        self.assertTrue(raw['presets']['tactical_next_dev']['hidden'])
        self.assertEqual(raw['presets']['tactical_next_dev']['extends'], 'tactical_next')

    def test_validation_rejects_broken_options(self):
        for path, value in (
                (('tactical', 'nuke', 'damage', 'areas'), [[4, 1.0], [3, 0.5], [10, 0.25]]),  # radius not growing
                (('tactical', 'nuke', 'damage', 'areas'), [[4, 0.2], [7, 0.5], [10, 0.25]]),  # fraction not falling
                (('tactical', 'nuke', 'damage', 'amount'), 0),
                (('tactical', 'nuke', 'range'), 101),
                (('tactical', 'grenade', 'hotkey'), 'g'),
                (('tactical', 'grenade', 'flight_speed'), 0),
                (('tactical', 'victory', 'types'), []),
                (('tactical', 'victory', 'types'), ['Barracks; drop']),
                (('tactical', 'rebel_labels', 'enabled'), 'yes')):
            cfg = clone(NEXT)
            node = cfg
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = value
            self.assertTrue(build.validate_config(cfg), path)


class NextData(unittest.TestCase):
    def setUp(self):
        self.frags = build.catalog_fragments(NEXT)
        for name, frag in self.frags.items():
            ET.fromstring('<Catalog>' + frag + '</Catalog>')

    def test_nuke_damage_profile_is_in_the_effect_fragment_only_when_configured(self):
        eff = self.frags['EffectData.xml']
        self.assertIn('<CEffectDamage id="NukeDamage">', eff)
        self.assertIn('<Amount value="600"/>', eff)
        self.assertIn('<AttributeBonus index="Structure" value="900"/>', eff)
        self.assertIn('<AreaArray index="2" Radius="10" Fraction="0.25"/>', eff)
        self.assertNotIn('<CEffectDamage id="NukeDamage">', build.catalog_fragments(OLD)['EffectData.xml'])

    def test_grenade_pointer_circle_and_effects(self):
        act = self.frags['ActorData.xml']
        for needle in ('GhostOpsAPCursorSplat', 'GhostOpsAPCursorModel', 'GhostOpsAPRange', 'GhostOpsAPImpact', 'GhostOpsAPSound', 'Effect.GhostOpsAPSearch.Impact'):
            self.assertIn(needle, act)
        self.assertNotIn('GhostOpsAPImpact', build.catalog_fragments(OLD).get('ActorData.xml', ''))
        self.assertIn('MaxSpeed="20"', self.frags['MoverData.xml']) if 'MoverData.xml' in self.frags else self.assertIn('MaxSpeed="20"', self.frags['UnitData.xml'] + self.frags['EffectData.xml'])

    def test_projectile_has_a_visible_missile_model(self):
        self.assertIn('<CModel id="GhostOpsAPMissile" parent="MissileBarragePod"/>', self.frags['ModelData.xml'])
        self.assertNotIn('ModelData.xml', build.catalog_fragments(OLD))  # the earlier profile is unchanged

    def test_hotkey_and_texts(self):
        entries = dict(build.text_entries(NEXT)['ruRU'])
        self.assertEqual(entries['Button/Hotkey/GhostOpsArmorPiercing'], 'G')
        self.assertEqual(dict(build.text_entries(OLD)['ruRU'])['Button/Hotkey/GhostOpsArmorPiercing'], 'E')
        for key in ('RebelTag', 'RebelMedicTag', 'RebelInfo', 'GrenadeEmpty', 'VictoryTitle', 'VictoryText', 'VictoryLeft'):
            self.assertIn(build.TAC_TEXT_PREFIX + key, entries)
        self.assertEqual(entries[build.TAC_TEXT_PREFIX + 'RebelTag'], 'Повстанец')
        self.assertIn('—', entries[build.TAC_TEXT_PREFIX + 'RebelInfo'])


class NextScript(unittest.TestCase):
    def test_block_is_ascii_lints_and_carries_the_options(self):
        block = build.build_block(ADAPTER, NEXT)
        block.encode('ascii')
        self.assertEqual(galaxy_lint.lint(block), [])
        for needle in ('go_tacRebelLabels = true;', 'go_tacVictory = true;', 'go_tacVicType[0] = "Barracks";', 'go_tacVicType[1] = "BarracksFlying";', 'go_tacMsgEmpty = true;'):
            self.assertIn(needle, block)
        old = build.build_block(ADAPTER, OLD)
        for needle in ('go_tacRebelLabels = false;', 'go_tacVictory = false;', 'go_tacMsgEmpty = false;'):
            self.assertIn(needle, old)

    def test_victory_counts_only_player_two_and_the_original_victory_is_called_once(self):
        ad = open(os.path.join(ROOT, 'adapters', 'traynor02', 'adapter.galaxy'), encoding='utf-8').read()
        self.assertIn('UnitGroup(go_tacVicType[lv_i], 2,', ad)  # the allied rebel barracks (another player) are not counted
        self.assertIn('go_tacVicSeen', ad)  # never an instant victory on an empty list
        tail = open(os.path.join(ROOT, 'adapters', 'traynor02', 'tail.galaxy'), encoding='utf-8').read()
        self.assertIn('gt_VictoryDominionOutpostCompleted_Func(false, true);', tail)
        self.assertIn('if (gv_gameOver)', tail)  # a second call does nothing
        self.assertEqual(ADAPTER['tail_source'], 'adapters/traynor02/tail.galaxy')

    def test_rebel_labels_follow_hide_and_are_drawn_again_after_a_load(self):
        mod = open(os.path.join(ROOT, 'core', 'GhostOpsTactical.galaxy'), encoding='utf-8').read()
        self.assertIn('TextTagCreate(lv_name, 12, UnitGetPosition(lp_unit), 0.0, true, false, PlayerGroupAll());', mod)  # not shown in the fog
        self.assertIn('TextTagAttachToUnit(TextTagLastCreated(), lp_unit, 1.8);', mod)  # follows the unit
        self.assertIn('GhostOps_Tac_RebelDestroyAll();', mod)  # a loaded game destroys the tags: they are drawn again by the tick, never doubled
        self.assertIn('if (GhostOps_Tac_RebelHas(lp_unit)', mod)
        self.assertIn('UnitSetInfoText(lp_unit, lv_name', mod)  # name / description of the unit, the Marine type is not renamed

    def test_panel_shows_the_real_charge_counter_and_the_death_of_the_operative(self):
        core = open(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), encoding='utf-8').read()
        self.assertIn('IntToText(go_pnGrenades)', core)
        self.assertIn('IntToText(go_pnGrenadeMax)', core)
        self.assertIn('GhostOpsPanel_Dead', core)


if __name__ == '__main__':
    unittest.main()
