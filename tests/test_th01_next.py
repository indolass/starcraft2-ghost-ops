"""THanson01 prepared detonations (preset sniper_next): config driven, the old sniper profile builds exactly as before."""
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

ADAPTER = build.load_adapter('thanson01')
NEXT, _ = build.resolve_config(ADAPTER, 'sniper_next')
OLD, _ = build.resolve_config(ADAPTER, 'sniper')


def clone(c):
    return json.loads(json.dumps(c))


class NextConfig(unittest.TestCase):
    def test_valid_numbers_and_separate_profile(self):
        self.assertEqual(build.validate_config(NEXT), [])
        self.assertEqual(NEXT['operatives']['squad'], ['Ghost', 'Ghost'])
        sn = NEXT['ghost_tuning']['snipe']
        self.assertEqual((sn['damage'], sn['cooldown'], sn['cost'], sn['cast_time']), (250, 2.0, 0, 0.3))  # the old 1000 / 1 is not carried over
        self.assertEqual(NEXT['ghost_tuning']['ghost_life'], 45)
        h = NEXT['hanson']
        self.assertEqual((h['containers']['limit'], h['containers']['gas_cost'], h['containers']['damage'], h['containers']['radius']), (12, 25, 200, 3.0))
        self.assertEqual(h['containers']['friendly'], {'hard': 0.25, 'other': 0.0})
        self.assertEqual(h['convoy_fuel']['gas_cost'], 100)
        self.assertTrue(h['lock_development'])  # no new production
        self.assertEqual(len(h['turrets']['list']), 15)  # the one fixed test kit
        self.assertEqual(OLD['operatives']['squad'], ['Ghost'])
        self.assertEqual(OLD['ghost_tuning']['snipe']['damage'], 1000)
        self.assertNotIn('containers', OLD['hanson'])

    def test_validation_rejects_broken_options(self):
        for path, value in (
                (('hanson', 'containers', 'limit'), -1),
                (('hanson', 'containers', 'friendly'), {'hard': 2, 'other': 0}),
                (('hanson', 'containers', 'hotkey'), 'c'),
                (('hanson', 'containers', 'owner'), 1),
                (('hanson', 'convoy_fuel', 'gas_cost'), -1),
                (('operatives', 'squad'), ['Ghost']),
                (('ghost_tuning', 'snipe', 'container_target'), False)):
            cfg = clone(NEXT)
            node = cfg
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = value
            self.assertTrue(build.validate_config(cfg), path)

    def test_lines_are_the_owner_texts_with_stable_ids(self):
        ids = [x['id'] for x in NEXT['hanson']['lines']]
        self.assertEqual(len(ids), len(set(ids)))
        ru = ' '.join(x['text']['ru'] for x in NEXT['hanson']['lines'])
        for needle in ('Подшаманил маскировку', 'банки с горючей смесью', 'Колонна выйдет по нашему приказу', 'рванёт прилично'):
            self.assertIn(needle, ru)
        self.assertIn('HARD_WARNING', ids)


class NextData(unittest.TestCase):
    def setUp(self):
        self.frags = build.catalog_fragments(NEXT)
        for frag in self.frags.values():
            ET.fromstring('<Catalog>' + frag + '</Catalog>')

    def test_container_is_a_neutral_biological_unit_placed_like_a_building(self):
        u = self.frags['UnitData.xml']
        for needle in ('GhostOpsFuelContainer', 'ExplodingBarrelLarge', '<Attributes index="Biological" value="1"/>', '<FlagArray index="Destructible" value="0"/>', 'GhostOpsPlaceContainer'):
            self.assertIn(needle, u)
        self.assertNotIn('<Footprint value=""/>', u)  # the stock footprint stays: the engine colours the placement (green / red) like a building
        a = self.frags['AbilData.xml']
        for needle in ('<PlaceUnit value="GhostOpsFuelContainer"/>', '<Placeholder value="GhostOpsFuelContainer"/>', '<Range value="4"/>'):
            self.assertIn(needle, a)
        cfg = clone(NEXT)
        cfg['hanson']['containers']['blank_footprint'] = True
        self.assertIn('<Footprint value=""/>', build.catalog_fragments(cfg)['UnitData.xml'])
        old = build.catalog_fragments(OLD)
        self.assertNotIn('GhostOpsFuelContainer', old.get('UnitData.xml', ''))

    def test_snipe_filter_opens_only_the_neutral_class(self):
        new = self.frags['AbilData.xml']
        self.assertIn('Self,Player,Ally,Structure,Destructible', new)
        self.assertNotIn('Ally,Neutral,Structure', new)
        self.assertIn('Ally,Neutral,Structure', build.catalog_fragments(OLD)['AbilData.xml'])  # the old profile refuses neutral targets as before

    def test_blast_effects(self):
        e = self.frags['EffectData.xml']
        self.assertIn('<AreaArray Radius="3" Effect="GhostOpsCBlastDamage"/>', e)
        self.assertIn('<Amount value="200"/>', e)
        self.assertIn('<Amount value="50"/>', e)  # own side on hard: 25 %
        self.assertIn('Ground;Player,Ally,Neutral,Air,', e)  # enemies: ground only, no air, no neutral (no chain)
        self.assertNotIn('GhostOpsCBlastOwnOther', e)  # multiplier 0 on the other difficulties: no effect at all
        cfg = clone(NEXT)
        cfg['hanson']['containers']['friendly']['hard'] = 0
        self.assertNotIn('GhostOpsCBlastOwnHard', build.catalog_fragments(cfg)['EffectData.xml'])

    def test_circles_and_visuals_are_actors_only(self):
        a = self.frags['ActorData.xml']
        for needle in ('GhostOpsCRadius', 'Behavior.GhostOpsContainerShow.On', 'GhostOpsCBlastModel', 'GhostOpsCBlastSound', 'GhostOpsCPointerSplat', 'Effect.GhostOpsCBlast.Impact'):
            self.assertIn(needle, a)

    def test_texts(self):
        ru = dict(build.text_entries(NEXT)['ruRU'])
        tip = ru['Button/Tooltip/GhostOpsPlaceContainer']
        for needle in ('25 газа', '12 штук', '200 урона', 'радиусе 3', '25%'):
            self.assertIn(needle, tip)
        self.assertEqual(ru['Button/Hotkey/GhostOpsPlaceContainer'], 'C')
        self.assertIn('Param/Value/GhostOpsH_L_SWANN_GHOSTS_1', ru)
        self.assertNotIn('Button/Name/GhostOpsPlaceContainer', dict(build.text_entries(OLD)['ruRU']))


class NextScript(unittest.TestCase):
    def test_block_lints_and_carries_the_options(self):
        block = build.build_block(ADAPTER, NEXT)
        block.encode('ascii')
        self.assertEqual(galaxy_lint.lint(block), [])
        for needle in ('go_hContOn = true;', 'go_hContLimit = 12;', 'go_hContCost = 25;', 'go_hFuelOn = true;', 'go_hFuelCost = 100;', 'go_hLnCount = 11;', 'go_hContFriendHard = 0.2500;'):
            self.assertIn(needle, block)
        old = build.build_block(ADAPTER, OLD)
        self.assertIn('go_hContOn = false;', old)
        self.assertIn('go_hFuelOn = false;', old)

    def test_the_rules_stay_in_the_code(self):
        m = open(os.path.join(ROOT, 'core', 'GhostOpsHanson.galaxy'), encoding='utf-8').read()
        self.assertIn('(UnitGetOwner(lv_k) == 1) || (UnitGetOwner(lv_k) == 4)', m)  # the first hit of ANY fighter of the player's side detonates it
        self.assertIn('c_unitAbilStageQueue', m)  # an order further than the placement range is cancelled when queued: the Firebat never walks across the map
        pay = 'PlayerModifyPropertyInt(1, c_playerPropVespene, c_playerPropOperSubtract, go_hFuelCost);'
        self.assertIn(pay, m)  # the fuel is paid once, in the accepted command
        i = m.index(pay)
        self.assertLess(m.index('if (GhostOps_Hanson_Gas() < go_hFuelCost)'), i)  # checked BEFORE the payment
        self.assertLess(i, m.index('go_hCmdState = 3;', i))  # the state changes after the payment
        self.assertLess(m.index('if (lv_why != 0) {'), m.index('UnitCreate(1, "GhostOpsFuelContainer"'))  # a refused placement returns before anything is created or charged
        self.assertEqual(m.count('c_playerPropOperSubtract, go_hContCost'), 1)  # one charge place for a container


if __name__ == '__main__':
    unittest.main()
