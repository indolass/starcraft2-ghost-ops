"""Evacuation (THanson01, revision 2) in the campaign: the pre-order of turret kits (recommended number, hint, price + preparation), paid once, and the order reaching the map build."""
import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402

PRESET = cf.step_of('thanson01')['preset']


class Fake:
    def __init__(self):
        self.running = False
        self.plans = []

    def sc2_running(self):
        return self.running

    def prepare(self, args, mode, progress):
        self.plans.append(args.plan)
        return 0

    def manifest(self, args):
        return {'data_hash': 'HK'}

    def start(self, args):
        return 0


class Kits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(self.tmp, 'campaign.json')
        os.environ['GHOSTOPS_BANK_DIR'] = self.tmp
        campaign.APP_DIR = self.tmp
        self.fake = Fake()
        self.flow = cf.CampaignFlow(self.fake)

    def tearDown(self):
        os.environ.pop('GHOSTOPS_CAMPAIGN_FILE', None)
        os.environ.pop('GHOSTOPS_BANK_DIR', None)

    def test_the_step_shows_the_recommended_number_and_where_to_cover(self):
        info = self.flow.order_info('thanson01', PRESET)
        self.assertEqual(info['items'], ['turret_kits'])
        self.assertEqual(info['recommended'], {'turret_kits': 15})
        self.assertIn('Рекомендуется 15', info['hint'])
        for needle in ('база', 'дома', 'воздушные'):
            self.assertIn(needle, info['hint'])
        self.assertEqual(info['recommended_cost'], {'minerals': 15 * 75 + 1000, 'gas': 500})

    def test_quote_limits_and_shortage_are_shown(self):
        q = self.flow.quote('thanson01', PRESET, {'turret_kits': 15})
        self.assertFalse(q['ok'])
        self.assertEqual(q['short'], {'minerals': 2125, 'gas': 500})
        self.assertTrue(self.flow.quote('thanson01', PRESET, {'turret_kits': 99})['errors'])
        self.assertTrue(self.flow.quote('thanson01', PRESET, {'turret_kits': 3, 'bunkers': 1})['errors'])

    def test_paid_once_and_the_order_reaches_the_map(self):
        s = self.flow.state()
        s['stock'] = {'minerals': 3000, 'gas': 600}
        campaign.commit(self.flow.path, s)
        ok, msg, op = self.flow.start_new('thanson01', PRESET, {'turret_kits': 6})
        self.assertTrue(ok, msg)
        self.assertEqual(self.flow.stock(), {'minerals': 3000 - (6 * 75 + 1000), 'gas': 100})
        again = self.flow.restart_operation(op)  # a restart of the paid operation: no second payment
        self.assertTrue(again[0])
        self.assertEqual(self.flow.stock(), {'minerals': 3000 - (6 * 75 + 1000), 'gas': 100})
        plan = json.load(open(self.fake.plans[0], encoding='utf-8'))
        self.assertEqual(plan['order'], {'turret_kits': 6})
        args = cf._args('thanson01', PRESET, self.fake.plans[0])
        adapter, cfg, _ = build.context(args)
        self.assertEqual(cfg['hanson']['turret_kits']['order'], {'turret_kits': 6})  # the plan overrides the default order
        self.assertIn('go_hKitOrdered = 6;', build.gen_hanson(cfg))
        self.assertEqual(cfg['campaign']['operation_id'], op)

    def test_the_card_launch_uses_the_recommended_order_as_a_test_budget(self):
        cfg, _ = build.resolve_config(build.load_adapter('thanson01'), PRESET)
        self.assertEqual(cfg['hanson']['turret_kits']['order'], {'turret_kits': 15})
        self.assertEqual(self.flow.stock(), {'minerals': 0, 'gas': 0})  # nothing is charged by a card launch


if __name__ == '__main__':
    unittest.main()


class Journal(unittest.TestCase):
    """The journal of THanson01: a victory is a proposal, a defeat never is (no income)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(self.tmp, 'campaign.json')
        os.environ['GHOSTOPS_BANK_DIR'] = self.tmp
        campaign.APP_DIR = self.tmp
        self.flow = cf.CampaignFlow(Fake())

    def tearDown(self):
        os.environ.pop('GHOSTOPS_CAMPAIGN_FILE', None)
        os.environ.pop('GHOSTOPS_BANK_DIR', None)

    def bank(self, rows):
        keys = ''.join('<Key name="e%d"><Value string="%s"/></Key>' % (i, r) for i, r in enumerate(rows, 1))
        open(campaign.bank_file(), 'w', encoding='utf-8').write('<Bank version="1"><Section name="j">%s</Section></Bank>' % keys)

    def test_defeat_offers_nothing_and_credits_nothing(self):
        s = self.flow.state()
        s['stock'] = {'minerals': 3000, 'gas': 700}
        campaign.commit(self.flow.path, s)
        ok, msg, op = self.flow.start_new('thanson01', PRESET, {'turret_kits': 2})
        self.assertTrue(ok, msg)
        stock = self.flow.stock()
        self.bank(['1|1.00|A9|START op=%s mission=thanson01 hash=HK startMin=200 startGas=50' % op,
                   '2|300.00|A9|DEFEAT op=%s mission=thanson01 hash=HK min=900 gas=10' % op])
        got = self.flow.after_exit()
        self.assertEqual(got['proposals'], [])
        self.assertEqual(self.flow.stock(), stock)

    def test_the_hooks_of_the_victory_and_the_defeats_exist(self):
        a = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'adapters', 'thanson01', 'adapter.json'), encoding='utf-8'))
        calls = {(h['function'], h['call']) for h in a['campaign_hooks']}
        self.assertIn(('gt_VictoryPlayerSavesEnoughColonists_Func', 'GhostOps_Camp_OnVictory();'), calls)
        for f in ('gt_DefeatBaseDead_Func', 'gt_DefeatTacticalPhase_Func', 'gt_DefeatColonyShipDead_Func', 'gt_DefeatColonistHutsDie_Func', 'gt_DefeatTooManyColonistsDie_Func'):
            self.assertIn((f, 'GhostOps_Camp_OnDefeat();'), calls)
