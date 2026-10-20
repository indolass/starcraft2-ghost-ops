"""Campaign flow of the launcher with a fake backend (no game, no build): pay once, unique set per operation, restart / continue without a second charge,
shortage shown, result proposal accepted once, a stale Bank file ignored."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402

ROWS = ['1|1.81|A111|START op=%(op)s mission=traynor02 hash=H1 startMin=100 startGas=0',
        '2|99.00|A111|RESULT op=%(op)s mission=traynor02 hash=H1 id=A111-5 outcome=victory min=1500 gas=40 startMin=100 startGas=0 minedMin=1400 minedGas=0 foundMin=0 foundGas=40 time=99']


class Fake:
    def __init__(self):
        self.running = False
        self.prepared = []
        self.started = []
        self.fail_prepare = False

    def sc2_running(self):
        return self.running

    def prepare(self, args, mode, progress):
        self.prepared.append((args.mission, args.plan, mode))
        return 9 if self.fail_prepare else 0

    def manifest(self, args):
        return {'data_hash': 'H1'}

    def start(self, args):
        self.started.append(args.plan)
        return 0


def write_bank(path, rows):
    keys = ''.join('<Key name="e%d"><Value string="%s"/></Key>' % (i, r) for i, r in enumerate(rows, 1))
    open(path, 'w', encoding='utf-8').write('<Bank version="1"><Section name="j">%s</Section></Bank>' % keys)


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(self.tmp, 'campaign.json')
        os.environ['GHOSTOPS_BANK_DIR'] = self.tmp
        campaign.APP_DIR = self.tmp  # plans and the bank archive stay in the test folder
        self.fake = Fake()
        self.flow = cf.CampaignFlow(self.fake)

    def tearDown(self):
        os.environ.pop('GHOSTOPS_CAMPAIGN_FILE', None)
        os.environ.pop('GHOSTOPS_BANK_DIR', None)

    def test_first_mission_has_no_purchase_and_no_charge(self):
        ok, msg, op = self.flow.start_new('traynor02', 'tactical')
        self.assertTrue(ok, msg)
        self.assertEqual(self.flow.stock(), {'minerals': 0, 'gas': 0})
        self.assertEqual(len(self.fake.started), 1)
        self.assertFalse(self.flow.start_new('traynor02', 'tactical')[0])  # an open operation: continue or restart, not a second order

    def test_result_acceptance_then_order_of_the_next_mission(self):
        ok, _, op = self.flow.start_new('traynor02', 'tactical')
        write_bank(os.path.join(self.tmp, 'GhostOpsCampaign.SC2Bank'), [r % {'op': op} for r in ROWS])
        got = self.flow.after_exit()
        self.assertEqual(len(got['proposals']), 1)
        report = self.flow.accept(got['proposals'][0])
        self.assertEqual(report['minerals']['remainder'], 1500)
        self.assertEqual(self.flow.stock(), {'minerals': 1500, 'gas': 40})
        self.assertEqual(self.flow.after_exit()['proposals'], [])  # the same journal is never accepted twice
        q = self.flow.quote('traynor03', 'standard', {'marines': 8, 'bunkers': 4, 'turrets': 4, 'scvs': 4})
        self.assertEqual(q['cost'], {'minerals': 1120, 'gas': 0})
        self.assertTrue(q['ok'])

    def test_shortage_is_shown_and_nothing_is_charged(self):
        order = {'marines': 8, 'bunkers': 4, 'turrets': 4, 'scvs': 4}
        ok, msg, _ = self.flow.start_new('traynor03', 'standard', order)
        self.assertFalse(ok)
        self.assertIn('1120 минералов', msg)
        self.assertEqual(self.flow.stock(), {'minerals': 0, 'gas': 0})
        self.assertEqual(self.fake.started, [])

    def test_limits_and_unknown_items_are_refused(self):
        s = self.flow.state()
        s['stock']['minerals'] = 5000
        campaign.commit(self.flow.path, s)
        self.assertFalse(self.flow.quote('traynor03', 'standard', {'marines': 99, 'bunkers': 4, 'turrets': 4, 'scvs': 4})['ok'])
        self.assertFalse(self.flow.quote('traynor03', 'standard', {'marines': 8, 'bunkers': 4, 'turrets': 4, 'scvs': 4, 'tanks': 1})['ok'])
        self.assertFalse(self.flow.quote('traynor03', 'standard', {'marines': -1, 'bunkers': 4, 'turrets': 4, 'scvs': 4})['ok'])

    def test_pay_once_then_restart_continue_and_failed_start_never_charge_again(self):
        s = self.flow.state()
        s['stock']['minerals'] = 2000
        campaign.commit(self.flow.path, s)
        order = {'marines': 8, 'bunkers': 4, 'turrets': 4, 'scvs': 4}
        self.fake.fail_prepare = True
        ok, msg, op = self.flow.start_new('traynor03', 'standard', order)
        self.assertFalse(ok)  # the build failed: the order stays PAID, nothing is lost
        self.assertEqual(self.flow.stock()['minerals'], 2000 - 1120)
        self.fake.fail_prepare = False
        self.assertTrue(self.flow.restart_operation(op)[0])
        self.assertTrue(self.flow.continue_operation(op)[0])
        self.assertEqual(self.flow.stock()['minerals'], 2000 - 1120)
        self.assertEqual(len([e for e in self.flow.state()['ledger'] if e['kind'] == 'charge']), 1)
        self.assertEqual(self.flow.state()['launch']['intent'], 'continue')
        plans = {p for m, p, mode in self.fake.prepared}
        self.assertEqual(len(plans), 1)  # always the same plan = the same set

    def test_running_game_is_never_touched(self):
        self.fake.running = True
        ok, msg, _ = self.flow.start_new('traynor02', 'tactical')
        self.assertFalse(ok)
        self.assertIn('не закрывает', msg)

    def test_a_bank_file_older_than_the_launch_is_stale(self):
        ok, _, op = self.flow.start_new('traynor02', 'tactical')
        bank = os.path.join(self.tmp, 'GhostOpsCampaign.SC2Bank')
        write_bank(bank, [r % {'op': op} for r in ROWS])
        old = time.time() - 3600
        os.utime(bank, (old, old))
        got = self.flow.after_exit()
        self.assertFalse(got['fresh'])
        self.assertEqual(got['proposals'], [])


if __name__ == '__main__':
    unittest.main()
