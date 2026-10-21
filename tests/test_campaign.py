"""Fault-injection tests of the launcher-side campaign accounting (tools/campaign.py; first written as the CE-0 prototype).
They prove the contract requirements of docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md 7 and 14 for the campaign accounting module."""
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import campaign as cp  # noqa: E402

H = 'abc123'


def fresh(tmp, minerals=5000, gas=2000):
    path = os.path.join(tmp, 'campaign_test.json')
    cp.commit(path, cp.new_campaign(minerals, gas))
    return path


def proposal(op='OP1', attempt='A1', rid='A1-1', outcome='victory', minerals=300, gas=40, h=H):
    return {'op': op, 'attempt': attempt, 'result_id': rid, 'data_hash': h, 'outcome': outcome, 'minerals': minerals, 'gas': gas}


class CampaignProto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = fresh(self.tmp)
        cp.plan_and_pay(self.path, 'OP1', 'thanson01', 'economy', {'minerals': 1000, 'gas': 500}, {}, H)
        cp.observe(self.path, [{'kind': 'START', 'op': 'OP1', 'attempt': 'A1'}])

    def stock(self):
        return cp.load(self.path)['stock']

    def test_charge_once(self):
        self.assertEqual(self.stock(), {'minerals': 4000, 'gas': 1500})
        for _ in range(3):  # a retry after a failed start, a load, a restart: never charged again
            cp.plan_and_pay(self.path, 'OP1', 'thanson01', 'economy', {'minerals': 1000, 'gas': 500}, {}, H)
        cp.observe(self.path, [{'kind': 'LOADED', 'op': 'OP1', 'attempt': 'A1'}, {'kind': 'START', 'op': 'OP1', 'attempt': 'A2'}])
        self.assertEqual(self.stock(), {'minerals': 4000, 'gas': 1500})
        self.assertEqual(len([e for e in cp.load(self.path)['ledger'] if e['kind'] == 'charge']), 1)

    def test_load_keeps_the_attempt_and_closing_the_game_changes_nothing(self):
        s, held = cp.observe(self.path, [{'kind': 'LOADED', 'op': 'OP1', 'attempt': 'A1'}])
        self.assertEqual(s['operations']['OP1']['attempts']['A1']['state'], 'live')
        self.assertEqual(held, [])
        # the same attempt can still deliver its result after "close the game, continue tomorrow"
        cp.accept(self.path, proposal())
        self.assertEqual(self.stock(), {'minerals': 4300, 'gas': 1540})

    def test_restart_makes_a_new_attempt_and_abandons_the_old_one(self):
        s, _ = cp.observe(self.path, [{'kind': 'START', 'op': 'OP1', 'attempt': 'A2'}])
        att = s['operations']['OP1']['attempts']
        self.assertEqual((att['A1']['state'], att['A2']['state']), ('abandoned', 'live'))
        with self.assertRaises(cp.Rejected):
            cp.accept(self.path, proposal(attempt='A1', rid='A1-9'))  # the abandoned attempt's result is not accepted automatically
        self.assertEqual(self.stock(), {'minerals': 4000, 'gas': 1500})
        cp.accept(self.path, proposal(attempt='A2', rid='A2-1', minerals=77, gas=0))
        self.assertEqual(self.stock(), {'minerals': 4077, 'gas': 1500})  # only the new attempt's remainder; nothing of the abandoned one

    def test_loading_an_abandoned_attempt_is_held_not_resumed(self):
        cp.observe(self.path, [{'kind': 'START', 'op': 'OP1', 'attempt': 'A2'}])
        s, held = cp.observe(self.path, [{'kind': 'LOADED', 'op': 'OP1', 'attempt': 'A1'}])
        self.assertEqual(len(held), 1)
        self.assertEqual(s['operations']['OP1']['attempts']['A1']['state'], 'abandoned')
        cp.explicit_resume(self.path, 'OP1', 'A1')  # only an explicit decision (open question of the Owner)
        cp.accept(self.path, proposal(attempt='A1', rid='A1-5'))

    def test_one_acceptance_per_result_and_per_operation(self):
        cp.accept(self.path, proposal())
        with self.assertRaises(cp.Rejected):
            cp.accept(self.path, proposal())  # the same result shown again
        with self.assertRaises(cp.Rejected):
            cp.accept(self.path, proposal(rid='A1-2', minerals=999))  # a second victory proposal of the same operation (load, win again)
        self.assertEqual(self.stock(), {'minerals': 4300, 'gas': 1540})

    def test_stale_foreign_and_wrong_build_proposals(self):
        for bad in (proposal(op='NOPE'), proposal(attempt='ZZ', rid='ZZ-1'), proposal(h='other'), proposal(minerals=-5)):
            with self.assertRaises(cp.Rejected):
                cp.accept(self.path, bad)
        self.assertEqual(self.stock(), {'minerals': 4000, 'gas': 1500})

    def test_defeat_changes_no_stock(self):
        cp.accept(self.path, proposal(outcome='defeat', rid='A1-3'))
        self.assertEqual(self.stock(), {'minerals': 4000, 'gas': 1500})
        self.assertEqual(cp.load(self.path)['operations']['OP1']['state'], 'reported')
        cp.accept(self.path, proposal(rid='A1-4'))  # the attempt is replayed from an earlier save and wins: still one acceptance
        self.assertEqual(self.stock(), {'minerals': 4300, 'gas': 1540})

    def test_atomic_commit_crash_points(self):
        """A failure at any point of the write gives neither a double reward nor a lost reward nor a half-written balance."""
        before = cp.load(self.path)
        for point in ('before_write', 'half_written', 'before_replace'):
            with self.assertRaises(cp.Crash):
                cp.accept(self.path, proposal(), crash_at=point)
            self.assertEqual(cp.load(self.path), before, point)  # recovery: the committed state is exactly the old one (the temp file is ignored)
            self.assertFalse(os.path.exists(self.path + '.tmp'))
        cp.accept(self.path, proposal())  # the retry after recovery credits exactly once
        self.assertEqual(self.stock(), {'minerals': 4300, 'gas': 1540})
        # a crash AFTER the replace: the new state is complete, the proposal shown again is rejected
        path2 = fresh(self.tmp)
        cp.plan_and_pay(path2, 'OP1', 'thanson01', 'economy', {'minerals': 1000, 'gas': 500}, {}, H)
        cp.observe(path2, [{'kind': 'START', 'op': 'OP1', 'attempt': 'A1'}])
        with self.assertRaises(cp.Crash):
            cp.accept(path2, proposal(), crash_at='after_replace')
        s = cp.load(path2)
        self.assertEqual(s['stock'], {'minerals': 4300, 'gas': 1540})
        self.assertIn('A1-1', s['accepted_results'])
        with self.assertRaises(cp.Rejected):
            cp.accept(path2, proposal())

    def test_charge_crash_leaves_no_half_charge(self):
        path = fresh(self.tmp)
        for point in ('before_write', 'half_written', 'before_replace'):
            with self.assertRaises(cp.Crash):
                cp.plan_and_pay(path, 'OPX', 'm', 'p', {'minerals': 1000, 'gas': 500}, {}, H, crash_at=point)
            s = cp.load(path)
            self.assertEqual(s['stock'], {'minerals': 5000, 'gas': 2000})
            self.assertNotIn('OPX', s['operations'])
        cp.plan_and_pay(path, 'OPX', 'm', 'p', {'minerals': 1000, 'gas': 500}, {}, H)
        self.assertEqual(cp.load(path)['stock'], {'minerals': 4000, 'gas': 1500})

    def test_journal_parsing_does_not_use_bank_sequence_numbers(self):
        rows = ['1|1.81|A1|START op=OP1 attempt=A1', '9|40.00|A1|LOADED op=OP1 attempt=A1 mem_n=7 mem_ext=',
                '9|99.00|A1|RESULT op=OP1 id=A1-555 hash=abc123 outcome=victory min=300 gas=40 marker=1']  # the number 9 repeats after a load
        recs, props = cp.parse_journal(rows)
        self.assertEqual([r['kind'] for r in recs], ['START', 'LOADED'])
        self.assertEqual((props[0]['result_id'], props[0]['minerals'], props[0]['gas']), ('A1-555', 300, 40))


REAL_ROWS = ['1|1.81|A938366144|START op=OP1 mission=traynor02 hash=abc123 startMin=100 startGas=0',
             '2|120.06|A938366144|RESULT op=OP1 mission=traynor02 hash=abc123 id=A938366144-891813522 outcome=victory min=210 gas=0 startMin=100 startGas=0 minedMin=110 minedGas=0 foundMin=0 foundGas=0 time=120',
             '3|120.06|A938366144|RESULT op=OP1 mission=traynor02 hash=abc123 id=A938366144-891813522 outcome=victory min=210 gas=0 startMin=100 startGas=0 minedMin=110 minedGas=0 foundMin=0 foundGas=0 time=120']


class Production(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = fresh(self.tmp)

    def test_real_rows_parse_dedupe_and_report(self):
        recs, props = cp.parse_journal(REAL_ROWS)
        self.assertEqual(len(props), 1)  # the map writes the proposal to both sections
        rep = cp.report(props[0])
        self.assertEqual(rep['minerals'], {'start': 100, 'mined': 110, 'found': 0, 'net_other_derived': 0, 'remainder': 210})
        self.assertIn('передано в кампанию 210', cp.report_lines(rep)[0])

    def test_continue_intent_ignores_the_process_own_start_and_fresh_restarts(self):
        cp.plan_and_pay(self.path, 'OP1', 'traynor02', 'tactical', {}, {}, 'abc123')
        cp.observe(self.path, cp.parse_journal(REAL_ROWS[:1])[0])
        new = [{'kind': 'START', 'op': 'OP1', 'attempt': 'B2', 'hash': 'abc123'}]
        s, held = cp.observe(self.path, new, intent='continue')  # the player loads an old save: the process's own START is not an attempt
        self.assertEqual(list(s['operations']['OP1']['attempts']), ['A938366144'])
        self.assertEqual(len(held), 1)
        s, _ = cp.observe(self.path, new, intent='fresh')  # a fresh launch: a full restart
        self.assertEqual({k: v['state'] for k, v in s['operations']['OP1']['attempts'].items()}, {'A938366144': 'abandoned', 'B2': 'live'})

    def test_insufficient_stock_is_shown_not_papered_over(self):
        with self.assertRaises(cp.Rejected) as e:
            cp.plan_and_pay(self.path, 'OP2', 'traynor03', 'standard', {'minerals': 9000, 'gas': 0}, {}, 'h')
        self.assertIn('missing 4000 minerals', str(e.exception))
        self.assertEqual(cp.load(self.path)['stock'], {'minerals': 5000, 'gas': 2000})

    def test_collect_ignores_a_stale_bank_file(self):
        import time
        bank = os.path.join(self.tmp, 'GhostOpsCampaign.SC2Bank')
        rows = ''.join('<Key name="e%d"><Value string="%s"/></Key>' % (i, r) for i, r in enumerate(REAL_ROWS, 1))
        open(bank, 'w', encoding='utf-8').write('<Bank version="1"><Section name="j">%s</Section></Bank>' % rows)
        cp.plan_and_pay(self.path, 'OP1', 'traynor02', 'tactical', {}, {}, 'abc123')
        got = cp.collect(self.path, 'OP1', time.time() + 100, bank=bank)  # the process was launched after the file was written
        self.assertFalse(got['fresh'])
        got = cp.collect(self.path, 'OP1', time.time() - 100, bank=bank)
        self.assertTrue(got['fresh'])
        self.assertEqual(len(got['proposals']), 1)


if __name__ == '__main__':
    unittest.main()
