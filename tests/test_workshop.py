"""Mission Workshop core (tools/workshop.py): supported fields, editing, validation, storage, frozen base, snapshot plan. No game is started and nothing is installed."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build  # noqa: E402
import workshop  # noqa: E402


class WorkshopCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get('GHOSTOPS_WORKSHOP_DIR')
        os.environ['GHOSTOPS_WORKSHOP_DIR'] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop('GHOSTOPS_WORKSHOP_DIR', None)
        else:
            os.environ['GHOSTOPS_WORKSHOP_DIR'] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)


class Fields(WorkshopCase):
    def test_only_the_mechanics_of_the_mission_are_offered(self):
        ids = lambda m: {f.id for f in workshop.supported_fields(m, workshop.base_cfg_of(workshop.new_variant(m, 'x')))}  # noqa: E731
        tr, th1, th2 = ids('traynor03'), ids('thanson01'), ids('thanson02')
        for need in ('garrison_dmg', 'rebel_dmg', 'nuke_count', 'grenade_charges', 'refinery', 'fp_on', 'det_margin', 'zh_marines', 'salvo_cd'):
            self.assertIn(need, tr)
        for no in ('snipe_cd', 'hell_tank', 'c_gas', 'transport'):
            self.assertNotIn(no, tr)  # not mechanics of Zero Hour
        for need in ('snipe_cd', 'c_gas', 'convoy_gas', 'th1_kits', 'th1_scvs', 'h_salvo_cd', 'det_margin'):
            self.assertIn(need, th1)
        for no in ('nuke_count', 'garrison_dmg', 'hell_tank', 'transport'):
            self.assertNotIn(no, th1)
        for need in ('hell_tank', 'truck_fuel', 'transport', 'perm_cloak', 'th2_bunkers', 'th2_marines', 'e_salvo_cd'):
            self.assertIn(need, th2)
        for no in ('nuke_count', 'snipe_cd', 'c_gas', 'th1_kits'):
            self.assertNotIn(no, th2)

    def test_every_field_path_exists_in_some_profile_and_is_stored_in_a_real_place(self):
        seen = set()
        for m in workshop.MISSIONS:
            v = workshop.new_variant(m, 'seen')
            for f in workshop.supported_fields(m, workshop.base_cfg_of(v)):
                seen.add(f.id)
        for f in workshop.FIELDS:
            self.assertIn(f.id, seen, 'field %s belongs to no mission profile: a field must reach a build' % f.id)

    def test_display_units(self):
        f = workshop.BY_ID['garrison_dmg']
        self.assertEqual(f.display(0.85), 85)
        self.assertAlmostEqual(f.store(120), 1.2)
        self.assertEqual(workshop.BY_ID['rebel_dmg'].display(1.2), 120)


class Editing(WorkshopCase):
    def test_changes_reach_the_effective_configuration_and_equal_values_are_not_recorded(self):
        v = workshop.new_variant('traynor03', 'v')
        base = workshop.base_cfg_of(v)
        workshop.set_field(v, 'garrison_dmg', 70)
        workshop.set_field(v, 'nuke_count', 2)
        workshop.set_field(v, 'grenade_charges', 6)
        cfg = workshop.effective_cfg(v)
        self.assertAlmostEqual(cfg['tactical']['garrison']['damage_multiplier'], 0.7)
        self.assertEqual(cfg['tactical']['nuke']['count'], 2)
        self.assertEqual(cfg['tactical']['grenade']['charges'], 6)
        self.assertEqual(base['tactical']['nuke']['count'], 1)  # the frozen base is untouched
        workshop.set_field(v, 'nuke_count', 1)  # equal to the base: nothing recorded
        self.assertNotIn('nuke_count', v['changes'])
        self.assertEqual(workshop.effective_cfg(v)['tactical']['nuke']['count'], 1)

    def test_order_and_recommendation_have_one_source(self):
        v = workshop.new_variant('traynor03', 'v')
        workshop.set_field(v, 'zh_marines', 20)
        cfg = workshop.effective_cfg(v)
        self.assertEqual(cfg['zerohour']['order']['marines'], 20)
        self.assertEqual(cfg['zerohour']['recommended'], cfg['zerohour']['order'])
        lines, _ = workshop.summary(v)
        self.assertIn('Морпехи: 20', lines)

    def test_permanent_cloak_zeroes_the_night_cost(self):
        v = workshop.new_variant('thanson02', 'v')
        workshop.set_field(v, 'perm_cloak', False)
        workshop.set_field(v, 'night_net', -2.5)
        self.assertEqual(workshop.effective_cfg(v)['epidemic']['night_cloak']['net_per_second'], -2.5)
        workshop.set_field(v, 'perm_cloak', True)
        self.assertEqual(workshop.effective_cfg(v)['epidemic']['night_cloak']['net_per_second'], 0)

    def test_reset_returns_to_the_base(self):
        v = workshop.new_variant('thanson01', 'v')
        workshop.set_field(v, 'snipe_cd', 2.5)
        workshop.reset_field(v, 'snipe_cd')
        self.assertEqual(workshop.effective_cfg(v)['ghost_tuning']['snipe']['cooldown'], workshop.base_cfg_of(v)['ghost_tuning']['snipe']['cooldown'])

    def test_summary_lists_the_differences_with_units(self):
        v = workshop.new_variant('thanson01', 'v')
        workshop.set_field(v, 'snipe_cd', 1.0)
        lines, diffs = workshop.summary(v)
        self.assertTrue(any('Перезарядка снайперского выстрела: 1.4 → 1 игровых секунд' in d for d in diffs), diffs)
        self.assertTrue(any('КСМ: 12 всего — 4 штатных + 8 добавленных' in ln for ln in lines), lines)
        self.assertTrue(any('бесплатный тест' in ln for ln in lines))


class Validation(WorkshopCase):
    def test_impossible_values_are_errors_unusual_ones_warnings(self):
        v = workshop.new_variant('traynor03', 'v')
        workshop.set_field(v, 'grenade_charges', 9)
        errs, _ = workshop.validate(v)
        self.assertTrue(any('Бронебойные заряды' in e for e in errs), errs)
        workshop.reset_field(v, 'grenade_charges')
        workshop.set_field(v, 'garrison_dmg', 400)
        errs, warns = workshop.validate(v)
        self.assertFalse(errs)
        self.assertTrue(any('Урон гарнизона' in w for w in warns), warns)

    def test_zones_must_grow_and_orders_obey_limits(self):
        v = workshop.new_variant('traynor03', 'v')
        workshop.set_field(v, 'nuke_r1', 14)
        errs, _ = workshop.validate(v)
        self.assertTrue(any('Радиусы зон' in e for e in errs), errs)
        workshop.reset_field(v, 'nuke_r1')
        workshop.set_field(v, 'zh_marines', 5)  # below the paid minimum of six
        errs, _ = workshop.validate(v)
        self.assertTrue(errs)

    def test_strong_variants_are_allowed(self):
        v = workshop.new_variant('thanson01', 'v')
        workshop.set_field(v, 'snipe_dmg', 900)
        workshop.set_field(v, 'snipe_cd', 0.5)
        errs, warns = workshop.validate(v)
        self.assertEqual(errs, [])
        self.assertTrue(warns)

    def test_every_untouched_base_is_valid(self):
        for m in workshop.MISSIONS:
            for n, _ in workshop.base_profiles(m):
                v = workshop.new_variant(m, 'b', n)
                self.assertEqual(workshop.validate(v)[0], [], (m, n))


class Storage(WorkshopCase):
    def test_roundtrip_and_listing_inside_the_mission(self):
        a = workshop.new_variant('thanson01', 'one')
        b = workshop.new_variant('thanson01', 'two')
        workshop.new_variant('traynor03', 'other')
        self.assertEqual([v['name'] for v in workshop.list_variants('thanson01')], ['one', 'two'])
        workshop.set_field(a, 'snipe_cd', 2.0)
        workshop.save(a)
        again = workshop.load('thanson01', a['id'])
        self.assertEqual(again['changes'], {'snipe_cd': 2.0})
        self.assertNotEqual(a['id'], b['id'])
        workshop.delete_draft(b)
        self.assertEqual([v['name'] for v in workshop.list_variants('thanson01')], ['one'])

    def test_a_later_change_of_the_base_does_not_change_the_variant(self):
        v = workshop.new_variant('thanson01', 'frozen')
        before = json.dumps(workshop.effective_cfg(v), sort_keys=True)
        real = workshop.resolved_base

        def changed(mission, base):
            c = real(mission, base)
            c['ghost_tuning']['snipe']['damage'] = 999
            return c
        workshop.resolved_base = changed
        try:
            self.assertEqual(json.dumps(workshop.effective_cfg(v), sort_keys=True), before)
            self.assertTrue(workshop.base_changed(v))
            workshop.refresh_base(v)
            self.assertEqual(workshop.effective_cfg(v)['ghost_tuning']['snipe']['damage'], 999)
        finally:
            workshop.resolved_base = real

    def test_free_profiles_only_as_a_base(self):
        with self.assertRaises(ValueError):
            workshop.new_variant('traynor03', 'x', 'defence_r5')  # a campaign profile
        with self.assertRaises(ValueError):
            workshop.new_variant('traynor03', '   ')


class SnapshotBuild(WorkshopCase):
    def test_the_plan_carries_the_full_configuration_and_the_map_has_its_own_name(self):
        v = workshop.new_variant('traynor03', 'plan')
        workshop.set_field(v, 'garrison_dmg', 70)
        cfg = workshop.effective_cfg(v)
        snap = json.loads(json.dumps(cfg))
        os.makedirs(os.path.join(self.tmp, 'traynor03'), exist_ok=True)
        pp = workshop.plan_path(v, 1)
        with open(pp, 'w', encoding='utf-8') as f:
            json.dump({'operation_id': workshop.op_id(v, 1), 'mission': 'traynor03', 'preset': v['base_preset'], 'snapshot': snap}, f)
        args = workshop.build_args(v, pp)
        adapter, cfg2, preset = build.context(args)
        self.assertEqual(cfg2['tactical']['garrison']['damage_multiplier'], 0.7)
        self.assertFalse(cfg2.get('campaign'))
        self.assertIn('__WK' + v['id'] + 'R1', build.output_name(adapter, preset))
        # nothing of the base profile reaches the build any more: a different profile name gives the same configuration
        args2 = workshop.build_args(v, pp)
        args2.preset = 'defence_r3_free'
        self.assertEqual(build.context(args2)[1], cfg2)

    def test_a_snapshot_with_a_campaign_part_is_refused(self):
        v = workshop.new_variant('thanson01', 'bad')
        snap = json.loads(json.dumps(workshop.effective_cfg(v)))
        snap['campaign'] = {'operation_id': 'X'}
        pp = workshop.plan_path(v, 1)
        os.makedirs(os.path.dirname(pp), exist_ok=True)
        with open(pp, 'w', encoding='utf-8') as f:
            json.dump({'operation_id': 'WKbadR1', 'mission': 'thanson01', 'preset': v['base_preset'], 'snapshot': snap}, f)
        with self.assertRaises(build.ConfigError):
            build.context(workshop.build_args(v, pp))

    def test_the_variant_build_is_accepted_by_the_generator(self):
        for m in workshop.MISSIONS:
            v = workshop.new_variant(m, 'gen')
            cfg = workshop.effective_cfg(v)
            self.assertEqual(build.validate_config(cfg), [])


if __name__ == '__main__':
    unittest.main()
