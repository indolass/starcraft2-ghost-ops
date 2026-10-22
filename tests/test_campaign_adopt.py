"""A result of a run that was started OUTSIDE the campaign (the launcher card): found, shown with exact numbers, adopted once, never twice; the other states say why."""
import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402

# the real journal of the Owner's run (2026-10-22), numbers as the map wrote them
ROWS = ['1|1.81|A676|START op=STANDALONE mission=traynor02 hash=2fbc909853f73d1c startMin=100 startGas=0',
        '2|280.56|A676|LOADED op=STANDALONE mission=traynor02 hash=2fbc909853f73d1c',
        '9|876.81|A676|RESULT op=STANDALONE mission=traynor02 hash=2fbc909853f73d1c id=A676-499 outcome=victory min=5636 gas=275 startMin=100 startGas=0 minedMin=5040 minedGas=0 foundMin=600 foundGas=300 time=877']


class Fake:
    def sc2_running(self):
        return False


def write_bank(path, rows, sections=('j', 'r')):
    out = '<?xml version="1.0" encoding="utf-8"?><Bank version="1">'
    for sec in sections:
        out += '<Section name="%s">%s</Section>' % (sec, ''.join('<Key name="e%d"><Value string="%s"/></Key>' % (i, r) for i, r in enumerate(rows, 1)))
    open(path, 'w', encoding='utf-8').write(out + '</Bank>')


class Adopt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(self.tmp, 'campaign.json')
        os.environ['GHOSTOPS_BANK_DIR'] = self.tmp
        campaign.APP_DIR = self.tmp
        self.bank = os.path.join(self.tmp, 'GhostOpsCampaign.SC2Bank')
        self.flow = cf.CampaignFlow(Fake())

    def tearDown(self):
        os.environ.pop('GHOSTOPS_CAMPAIGN_FILE', None)
        os.environ.pop('GHOSTOPS_BANK_DIR', None)

    def test_new_operations_use_the_current_version_old_ones_keep_theirs(self):
        self.assertEqual(cf.step_of('traynor02')['preset'], 'tactical_next')
        campaign.plan_and_pay(self.flow.path, 'OP0001', 'traynor02', 'tactical', {}, {}, 'H')
        self.assertEqual(self.flow.state()['operations']['OP0001']['profile'], 'tactical')  # an earlier operation is not rewritten

    def test_found_result_shows_exact_numbers_and_source(self):
        write_bank(self.bank, ROWS)
        st = self.flow.standalone_status('traynor02')
        self.assertEqual(st['state'], 'found')
        self.assertIn('ожидает принятия', st['text'])
        self.assertEqual(len(st['results']), 1)  # written into both sections, ONE result
        p = st['results'][0]
        self.assertEqual((p['minerals'], p['gas']), (5636, 275))
        self.assertEqual(p['start'], {'minerals': 100, 'gas': 0})
        self.assertEqual((p['mined']['minerals'], p['found']['minerals'], p['found']['gas']), (5040, 600, 300))
        self.assertEqual(p['source'], self.bank)
        self.assertEqual(self.flow.stock(), {'minerals': 0, 'gas': 0})  # nothing changes before the player confirms

    def test_adoption_is_one_atomic_and_once_only(self):
        write_bank(self.bank, ROWS)
        p = self.flow.standalone_status('traynor02')['results'][0]
        rep = self.flow.adopt_standalone(p)
        self.assertEqual(rep['minerals']['remainder'], 5636)
        self.assertEqual(self.flow.stock(), {'minerals': 5636, 'gas': 275})
        s = self.flow.state()
        self.assertEqual(s['accepted_results'], ['A676-499'])
        self.assertEqual(s['ledger'][-1]['kind'], 'return_standalone')
        self.assertEqual(self.flow.accepted_operation('traynor02')[0], 'SA-A676-499')
        with self.assertRaises(campaign.Rejected):
            self.flow.adopt_standalone(p)  # a second click, a second window: nothing happens
        self.assertEqual(self.flow.stock(), {'minerals': 5636, 'gas': 275})
        self.assertEqual(self.flow.standalone_status('traynor02')['state'], 'accepted')
        self.assertIn('уже зачислен', self.flow.standalone_status('traynor02')['text'])

    def test_a_crash_inside_the_commit_changes_nothing_or_everything(self):
        write_bank(self.bank, ROWS)
        p = self.flow.standalone_status('traynor02')['results'][0]
        for point in ('before_write', 'half_written', 'before_replace'):
            with self.assertRaises(campaign.Crash):
                campaign.adopt_standalone(self.flow.path, p, 'tactical_next', crash_at=point)
            self.assertEqual(self.flow.stock(), {'minerals': 0, 'gas': 0}, point)
            self.assertEqual(self.flow.state()['accepted_results'], [], point)
        with self.assertRaises(campaign.Crash):
            campaign.adopt_standalone(self.flow.path, p, 'tactical_next', crash_at='after_replace')
        s = self.flow.state()  # the write happened: stock and mark are together
        self.assertEqual((s['stock']['minerals'], s['accepted_results']), (5636, ['A676-499']))

    def test_archived_copy_of_the_same_journal_is_not_a_second_result(self):
        write_bank(self.bank, ROWS)
        os.makedirs(campaign.archive_dir())
        write_bank(os.path.join(campaign.archive_dir(), 'GhostOpsCampaign_1.SC2Bank'), ROWS)
        self.assertEqual(len(self.flow.standalone_status('traynor02')['results']), 1)

    def test_not_connected_and_not_found_say_why(self):
        st = self.flow.standalone_status('traynor02')
        self.assertEqual(st['state'], 'not_found')
        self.assertIn('отсутствует', st['text'])
        write_bank(self.bank, [])
        self.assertIn('нет записей', self.flow.standalone_status('traynor02')['text'])
        write_bank(self.bank, ROWS[:2])  # started and loaded, never won
        st = self.flow.standalone_status('traynor02')
        self.assertEqual(st['state'], 'not_connected')
        self.assertIn('не подключено к кампании', st['text'])
        write_bank(self.bank, [ROWS[0], ROWS[2].replace('outcome=victory', 'outcome=defeat')])
        p = self.flow.standalone_status('traynor02')
        self.assertEqual(p['state'], 'not_connected')  # a defeat is never adopted
        with self.assertRaises(campaign.Rejected):
            campaign.adopt_standalone(self.flow.path, dict(campaign.parse_journal([ROWS[2].replace('outcome=victory', 'outcome=defeat')])[1][0]), 'x')

    def test_a_mission_with_an_accepted_operation_cannot_be_adopted_again(self):
        write_bank(self.bank, ROWS)
        campaign.plan_and_pay(self.flow.path, 'OP0001', 'traynor02', 'tactical', {}, {}, 'H')
        s = self.flow.state()
        s['operations']['OP0001']['state'] = 'accepted'
        campaign.commit(self.flow.path, s)
        st = self.flow.standalone_status('traynor02')
        self.assertTrue(st['blocked'])
        with self.assertRaises(campaign.Rejected):
            self.flow.adopt_standalone(st['results'][0])

    def test_the_window_draws_the_four_states(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools', 'gui_campaign.py'), encoding='utf-8').read()
        for needle in ('Зачислить в кампанию (один раз)', 'ровно: %d минералов, %d газа', 'Источник: журнал карты', 'cf.step_of(\'traynor02\')[\'preset\']'):
            self.assertIn(needle, src)


if __name__ == '__main__':
    unittest.main()
