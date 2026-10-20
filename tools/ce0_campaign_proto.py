"""CE-0 ISOLATED PROTOTYPE of the launcher-side campaign accounting (docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md, 7.1, 7.6, 7.7).

Nothing here is used by the launcher, the build or any playable profile. It exists to prove, with fault injection, the rules the contract
states as requirements: one charge per operation, attempts that survive a load and are replaced by a restart, a result proposal that is
accepted at most once, rejection of stale / abandoned / foreign proposals, and ONE atomic write of "stock change + accepted mark".
The state file is a separate TEST file given by the caller; the Owner's campaign (none exists yet) and the launcher settings are never touched.

Records come from the map's journal (Bank GhostOpsCe0, see core/GhostOpsCe0.galaxy): START / LOADED / SAVEGAME lines and RESULT proposals.
"""
import json
import os
import re

STATES = ('planned', 'paid', 'started', 'reported', 'accepted', 'abandoned', 'failed_to_start')


class Rejected(Exception):
    """A proposal that must not change the campaign (the reason is the message)."""


class Crash(Exception):
    """Injected failure of the storage (tests only)."""


def new_campaign(minerals, gas):
    return {'stock': {'minerals': minerals, 'gas': gas}, 'ledger': [], 'operations': {}, 'accepted_results': []}


def load(path):
    """Reads the state. A leftover temporary file of an interrupted write is ignored (and removed): the committed file is the truth."""
    tmp = path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def commit(path, state, crash_at=None):
    """ONE atomic operation: write a temporary file, flush it to disk, replace the committed file. The stock, the ledger, the attempts and the
    accepted marks are all in this one file, so a reader sees either the whole old state or the whole new state. `crash_at` injects a failure
    ('before_write', 'half_written', 'before_replace', 'after_replace')."""
    if crash_at == 'before_write':
        raise Crash(crash_at)
    data = json.dumps(state, indent=1, sort_keys=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if crash_at == 'half_written':
            f.write(data[:len(data) // 2])
            f.flush()
            raise Crash(crash_at)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if crash_at == 'before_replace':
        raise Crash(crash_at)
    os.replace(tmp, path)
    if crash_at == 'after_replace':
        raise Crash(crash_at)


# ---- operation life ------------------------------------------------------------------------------------------------------------------------
def plan_and_pay(path, operation_id, mission, profile, cost, handed, data_hash, crash_at=None):
    """planned -> paid. The charge is keyed by operation_id: calling this again (a retry after a failed start) charges nothing."""
    s = load(path)
    op = s['operations'].get(operation_id)
    if op is not None:
        return s
    stock = s['stock']
    need = {k: cost.get(k, 0) + handed.get(k, 0) for k in ('minerals', 'gas')}
    if any(stock[k] < need[k] for k in need):
        raise Rejected('not enough stock')
    for k in need:
        stock[k] -= need[k]
    s['ledger'].append({'op': operation_id, 'kind': 'charge', 'cost': cost, 'handed': handed})
    s['operations'][operation_id] = {'mission': mission, 'profile': profile, 'cost': cost, 'handed': handed, 'data_hash': data_hash,
                                     'state': 'paid', 'attempts': {}, 'accepted_result': None}
    commit(path, s, crash_at)
    return s


def observe(path, records):
    """Applies journal records of the map to the attempt list. START of an unknown attempt of an operation = a fresh run: the earlier live
    attempts of that operation become abandoned (a full restart); LOADED of a known live attempt = it continues (no charge, no new attempt);
    LOADED of an abandoned attempt is NOT resumed automatically (held for the Owner's decision). Closing the game changes nothing."""
    s = load(path)
    held = []
    for r in records:
        op = s['operations'].get(r['op'])
        if op is None or op['state'] in ('accepted',):
            continue
        if r['kind'] == 'START':
            if r['attempt'] in op['attempts']:
                continue
            for a in op['attempts'].values():
                if a['state'] == 'live':
                    a['state'] = 'abandoned'
            op['attempts'][r['attempt']] = {'state': 'live'}
            op['state'] = 'started'
        elif r['kind'] == 'LOADED':
            a = op['attempts'].get(r['attempt'])
            if a is None:
                held.append(('unknown attempt loaded', r))
            elif a['state'] == 'abandoned':
                held.append(('abandoned attempt loaded: not resumed automatically', r))
    commit(path, s)
    return s, held


def explicit_abandon(path, operation_id, attempt):
    s = load(path)
    s['operations'][operation_id]['attempts'][attempt]['state'] = 'abandoned'
    commit(path, s)


def explicit_resume(path, operation_id, attempt):
    """The player explicitly resumes an abandoned attempt (the Owner's decision on whether this exists at all is open)."""
    s = load(path)
    op = s['operations'][operation_id]
    if op['state'] == 'accepted':
        raise Rejected('operation already accepted')
    for a in op['attempts'].values():
        if a['state'] == 'live':
            a['state'] = 'abandoned'
    op['attempts'][attempt]['state'] = 'live'
    commit(path, s)


def accept(path, proposal, crash_at=None):
    """The launcher side accepts a result proposal {op, attempt, result_id, data_hash, outcome, minerals, gas} - or rejects it by exception.
    The returned remainder and the 'accepted' mark are written by ONE commit."""
    s = load(path)
    op = s['operations'].get(proposal['op'])
    if op is None:
        raise Rejected('unknown operation')
    if proposal['result_id'] in s['accepted_results']:
        raise Rejected('this result was already accepted')
    if op['state'] == 'accepted':
        raise Rejected('the operation already has an accepted result')
    if op['state'] not in ('started', 'reported'):
        raise Rejected('operation is %s' % op['state'])
    a = op['attempts'].get(proposal['attempt'])
    if a is None:
        raise Rejected('the attempt does not belong to this operation')
    if a['state'] == 'abandoned':
        raise Rejected('result of an abandoned attempt is never accepted automatically')
    if proposal['data_hash'] != op['data_hash']:
        raise Rejected('data_hash differs from the immutable set')
    if proposal['outcome'] != 'victory':
        a['state'] = 'ended'
        op['state'] = 'reported'
        commit(path, s, crash_at)
        return s
    for k in ('minerals', 'gas'):
        if proposal[k] < 0:
            raise Rejected('negative resource')
        s['stock'][k] += proposal[k]
    s['ledger'].append({'op': proposal['op'], 'kind': 'return', 'result_id': proposal['result_id'], 'minerals': proposal['minerals'], 'gas': proposal['gas']})
    s['accepted_results'].append(proposal['result_id'])
    op['accepted_result'] = proposal['result_id']
    op['state'] = 'accepted'
    a['state'] = 'ended'
    commit(path, s, crash_at)
    return s


# ---- the map's journal ---------------------------------------------------------------------------------------------------------------------
_ROW = re.compile(r'(\d+)\|([\d.]+)\|(\w*)\|(.*)')


def parse_journal(rows):
    """rows: iterable of the strings of the Bank journal sections j / r. Returns START / LOADED records and RESULT proposals.
    The sequence number of the Bank is NOT used as an order or as an id: a load restores the Bank to its saved state, so numbers repeat."""
    records, proposals = [], []
    for text in rows:
        m = _ROW.match(text)
        if not m:
            continue
        attempt, body = m.group(3), m.group(4)
        mo = re.match(r'(START|LOADED) op=(\S+) attempt=(\S+)', body)
        if mo:
            records.append({'kind': mo.group(1), 'op': mo.group(2), 'attempt': mo.group(3)})
        mr = re.match(r'RESULT op=(\S+) id=(\S+) hash=(\w*) outcome=(\S+) min=(\d+) gas=(\d+)', body)
        if mr:
            proposals.append({'op': mr.group(1), 'attempt': attempt, 'result_id': mr.group(2), 'data_hash': mr.group(3), 'outcome': mr.group(4),
                              'minerals': int(mr.group(5)), 'gas': int(mr.group(6)), 'mission_time': m.group(2)})
    return records, proposals
