"""CE-0 evidence: the isolated accounting prototype driven by REAL bank files written by the game (test files only).

  python tools/ce0_proto_e2e.py BANK_FIRST.xml BANK_SECOND.xml
BANK_FIRST: a bank of a finished attempt (with a RESULT proposal); BANK_SECOND: the bank of a later launch of the same operation.
The data hash of the build is taken from the proposal itself (a real launcher would take it from the immutable set)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce0_campaign_proto as cp  # noqa: E402
import ce0_session  # noqa: E402


def rows_of(bank_path):
    b = ce0_session.read_bank(bank_path)
    return [v for sec in ('j', 'r') for k, v in b.get(sec, {}).items()]


def main(first, second):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, 'campaign_test.json')
    cp.commit(path, cp.new_campaign(5000, 2000))
    rec1, prop1 = cp.parse_journal(rows_of(first))
    op = rec1[0]['op']
    h = prop1[0]['data_hash']
    cp.plan_and_pay(path, op, 'traynor02', 'ce0_dev', {'minerals': 0, 'gas': 0}, {}, h)
    cp.observe(path, rec1)
    print('stock before:', cp.load(path)['stock'])
    p = dict(prop1[0])
    print('proposal 1:', p)
    s = cp.accept(path, p)
    print('accepted 1 -> stock', s['stock'], 'state', s['operations'][op]['state'])
    for label, f in (('same proposal again', lambda: cp.accept(path, p)),):
        try:
            f()
        except cp.Rejected as e:
            print(label, '-> rejected:', e)
    rec2, prop2 = cp.parse_journal(rows_of(second))
    s, held = cp.observe(path, rec2)
    print('second launch attempts:', {k: v['state'] for k, v in s['operations'][op]['attempts'].items()}, 'held:', held)
    try:
        cp.accept(path, dict(prop2[0]))
    except cp.Rejected as e:
        print('proposal 2 (a second victory of the same operation) -> rejected:', e)
    print('stock after:', cp.load(path)['stock'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
