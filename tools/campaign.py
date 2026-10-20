"""Launcher-side campaign state of Ghost Ops (contract: docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md, sections 7 and 14).

The map owns nothing of the campaign: it writes a small journal into the Bank `GhostOpsCampaign` (core/GhostOpsCampaign.galaxy) and the launcher decides what is
accepted. Facts this design rests on (measured in the installed game, docs/RESEARCH.md "CE-0"): a load restores the Bank to its saved state, so the Bank sequence is
never an id; the attempt identity is a saved global; closing the game keeps the last written record; the launcher must only READ the Bank.

State file: `%APPDATA%\\GhostOps\\campaign.json` (override: env GHOSTOPS_CAMPAIGN_FILE - tests always use their own file). ONE atomic write changes the stock and
marks a result accepted together (temporary file, flush, os.replace); a leftover temporary file is ignored on the next read.
"""
import json
import os
import re
import shutil
import time

APP_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'GhostOps')
DEFAULT_PATH = os.path.join(APP_DIR, 'campaign.json')
DOCS = os.path.join(os.path.expanduser('~'), 'Documents', 'StarCraft II')
BANK_NAME = 'GhostOpsCampaign'
STANDALONE = 'STANDALONE'          # the operation id of builds that are not part of the campaign (practice, standalone tests)
RES = ('minerals', 'gas')


class Rejected(Exception):
    """A proposal or a plan that must not change the campaign (the reason is the message)."""


class Crash(Exception):
    """Injected failure of the storage (tests only)."""


def campaign_path():
    return os.environ.get('GHOSTOPS_CAMPAIGN_FILE') or DEFAULT_PATH


def bank_dir():
    return os.environ.get('GHOSTOPS_BANK_DIR') or os.path.join(DOCS, 'Banks')


def bank_file():
    return os.path.join(bank_dir(), BANK_NAME + '.SC2Bank')


def new_campaign(minerals=0, gas=0):
    return {'version': 1, 'stock': {'minerals': minerals, 'gas': gas}, 'ledger': [], 'operations': {}, 'accepted_results': [], 'launch': None}


def load(path=None):
    """Reads the state. A leftover temporary file of an interrupted write is ignored (and removed): the committed file is the truth."""
    path = path or campaign_path()
    tmp = path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_or_create(path=None):
    path = path or campaign_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        commit(path, new_campaign())
    return load(path)


def commit(path, state, crash_at=None):
    """ONE atomic operation (stock, ledger, attempts and accepted marks are all in this one file). `crash_at` injects a failure for tests:
    'before_write', 'half_written', 'before_replace', 'after_replace'."""
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


# ---- operations ----------------------------------------------------------------------------------------------------------------------------
def plan_and_pay(path, operation_id, mission, profile, cost, handed, data_hash, order=None, crash_at=None):
    """planned -> paid. The charge is keyed by operation_id: calling it again (a retry after a failed start) charges nothing. `cost` is what the
    chosen order costs (validated by the caller against the resolved prices and limits); `handed` is stock given to the surface (kept apart)."""
    s = load(path)
    if operation_id in s['operations']:
        return s
    need = {k: int(cost.get(k, 0)) + int(handed.get(k, 0)) for k in RES}
    if any(v < 0 for v in need.values()):
        raise Rejected('negative amount')
    short = {k: need[k] - s['stock'][k] for k in RES if need[k] > s['stock'][k]}
    if short:
        raise Rejected('not enough stock (missing %s)' % ', '.join('%d %s' % (v, k) for k, v in short.items()))
    for k in RES:
        s['stock'][k] -= need[k]
    s['ledger'].append({'op': operation_id, 'kind': 'charge', 'cost': cost, 'handed': handed})
    s['operations'][operation_id] = {'mission': mission, 'profile': profile, 'cost': cost, 'handed': handed, 'data_hash': data_hash, 'order': order,
                                     'state': 'paid', 'attempts': {}, 'accepted_result': None, 'created': time.time()}
    commit(path, s, crash_at)
    return s


def set_data_hash(path, operation_id, data_hash):
    """The build of a paid operation fixes its data hash (a failed build leaves the paid order as it is)."""
    s = load(path)
    s['operations'][operation_id]['data_hash'] = data_hash
    commit(path, s)


def abandon_operation(path, operation_id):
    """An explicit refusal of the player (never a closed game). Whether the cost returns is an Owner decision (open): nothing is refunded here."""
    s = load(path)
    op = s['operations'][operation_id]
    if op['state'] == 'accepted':
        raise Rejected('operation already accepted')
    for a in op['attempts'].values():
        if a['state'] == 'live':
            a['state'] = 'abandoned'
    op['state'] = 'abandoned'
    commit(path, s)


def explicit_abandon(path, operation_id, attempt):
    s = load(path)
    s['operations'][operation_id]['attempts'][attempt]['state'] = 'abandoned'
    commit(path, s)


def explicit_resume(path, operation_id, attempt):
    """The player explicitly resumes an abandoned attempt (whether this exists at all is an open Owner decision)."""
    s = load(path)
    op = s['operations'][operation_id]
    if op['state'] == 'accepted':
        raise Rejected('operation already accepted')
    for a in op['attempts'].values():
        if a['state'] == 'live':
            a['state'] = 'abandoned'
    op['attempts'][attempt]['state'] = 'live'
    commit(path, s)


# ---- the map's journal -----------------------------------------------------------------------------------------------------------------------
_ROW = re.compile(r'(\d+)\|([\d.]+)\|(\w*)\|(\w+) (.*)')


def _kv(text):
    return dict(re.findall(r'(\w+)=(\S*)', text))


def parse_journal(rows):
    """rows: strings of the Bank sections j / r (`seq|time|attempt|KIND key=value ...`). Returns (records, proposals). The Bank sequence is NOT used as an
    order or an id (a load restores the Bank, so numbers repeat). Records keep the order of the rows as given."""
    records, proposals = [], []
    for text in rows:
        m = _ROW.match(text)
        if not m:
            continue
        kind, kv = m.group(4), _kv(m.group(5))
        if kind in ('START', 'LOADED', 'DEFEAT') and 'op' in kv:
            records.append({'kind': kind, 'op': kv['op'], 'attempt': m.group(3), 'mission': kv.get('mission'), 'hash': kv.get('hash'), 'time': m.group(2)})
        elif kind == 'RESULT' and 'op' in kv and 'id' in kv:
            def num(k):
                return int(kv.get(k, '0') or 0)
            proposals.append({'op': kv['op'], 'attempt': m.group(3), 'result_id': kv['id'], 'data_hash': kv.get('hash'), 'outcome': kv.get('outcome', 'victory'),
                              'minerals': num('min'), 'gas': num('gas'), 'start': {'minerals': num('startMin'), 'gas': num('startGas')},
                              'mined': {'minerals': num('minedMin'), 'gas': num('minedGas')}, 'found': {'minerals': num('foundMin'), 'gas': num('foundGas')},
                              'mission_time': m.group(2), 'mission': kv.get('mission')})
    seen, unique = set(), []
    for p in proposals:  # the map writes the proposal into both sections of the journal
        if p['result_id'] not in seen:
            seen.add(p['result_id'])
            unique.append(p)
    return records, unique


def read_bank(path=None):
    """{section: {key: string}} of an SC2Bank file. Read only (the game breaks when another process edits its Bank)."""
    import xml.etree.ElementTree as ET
    path = path or bank_file()
    out = {}
    root = ET.parse(path).getroot()
    for sec in root.findall('Section'):
        d = out.setdefault(sec.get('name'), {})
        for key in sec.findall('Key'):
            v = key.find('Value')
            if v is not None:
                d[key.get('name')] = v.get('string') or v.get('int') or ''
    return out


def journal_rows(bank=None):
    """The journal rows of the Bank file in the order the map wrote them (the numeric part of the key; it can repeat after a load, so a stable sort keeps file order)."""
    try:
        b = read_bank(bank)
    except (OSError, ValueError, Exception):
        return []
    rows = []
    for sec in ('j', 'r'):
        for k, v in b.get(sec, {}).items():
            rows.append((int(re.sub(r'\D', '', k) or 0), v))
    rows.sort(key=lambda r: r[0])
    return [v for _, v in rows]


def archive_bank(archive_dir=None):
    """Before a launch the launcher starts: move the old Bank file away (never edit it). Returns the new path or None."""
    src = bank_file()
    if not os.path.exists(src):
        return None
    archive_dir = archive_dir or os.path.join(APP_DIR, 'bank_archive')
    os.makedirs(archive_dir, exist_ok=True)
    dst = os.path.join(archive_dir, '%s_%d.SC2Bank' % (BANK_NAME, int(time.time() * 1000)))
    shutil.move(src, dst)
    return dst


def begin_launch(path, operation_id, intent):
    """The launcher records WHY it starts the game: `fresh` (a new attempt is expected) or `continue` (the player continues a saved attempt)."""
    if intent not in ('fresh', 'continue'):
        raise ValueError(intent)
    s = load(path)
    s['launch'] = {'op': operation_id, 'intent': intent, 'at': time.time()}
    commit(path, s)


def observe(path, records, intent='fresh'):
    """Applies the journal of a finished (or running) game to the attempt list of the operation. The ACTIVE attempt is the attempt of the LAST record:
    - an unknown attempt with intent `fresh` = a fresh start / full restart: earlier live attempts of the operation become `abandoned`;
    - an unknown attempt with intent `continue` = the process's own start before the save was loaded: ignored;
    - a known live attempt = it continues (a load of its save): no charge, no new attempt;
    - an abandoned attempt that is loaded again is HELD (not resumed automatically).
    Closing the game changes nothing."""
    s = load(path)
    held = []
    last = {}
    for r in records:
        last[r['op']] = r
    for op_id, r in last.items():
        op = s['operations'].get(op_id)
        if op is None or op['state'] in ('accepted', 'abandoned'):
            continue
        a = op['attempts'].get(r['attempt'])
        if a is None:
            if intent == 'continue':
                held.append(('unknown attempt while continuing: not tracked', r))
                continue
            for x in op['attempts'].values():
                if x['state'] == 'live':
                    x['state'] = 'abandoned'
            op['attempts'][r['attempt']] = {'state': 'live', 'hash': r.get('hash')}
            if op['state'] in ('paid', 'started'):
                op['state'] = 'started'
        elif a['state'] == 'abandoned':
            held.append(('abandoned attempt is the active one: not resumed automatically', r))
    commit(path, s)
    return s, held


def accept(path, proposal, crash_at=None):
    """The launcher side accepts a result proposal or rejects it by exception. The remainder and the 'accepted' mark are ONE commit."""
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
    for k in RES:
        if proposal[k] < 0:
            raise Rejected('negative resource')
    for k in RES:
        s['stock'][k] += proposal[k]
    s['ledger'].append({'op': proposal['op'], 'kind': 'return', 'result_id': proposal['result_id'], 'minerals': proposal['minerals'], 'gas': proposal['gas']})
    s['accepted_results'].append(proposal['result_id'])
    op['accepted_result'] = proposal['result_id']
    op['report'] = report(proposal)
    op['state'] = 'accepted'
    a['state'] = 'ended'
    commit(path, s, crash_at)
    return s


def report(p):
    """The end-of-mission report. Start, mined (native counter), found (resource pallets, counted) and the remainder are measured; the net of everything else
    (spending, grants that are not counted) is DERIVED and named so: nothing is invented."""
    r = {}
    for k, label in (('minerals', 'minerals'), ('gas', 'gas')):
        st, mi, fo = (p.get('start') or {}).get(k, 0), (p.get('mined') or {}).get(k, 0), (p.get('found') or {}).get(k, 0)
        r[k] = {'start': (p.get('start') or {}).get(k, 0), 'mined': mi, 'found': fo, 'net_other_derived': st + mi + fo - p[k], 'remainder': p[k]}
    return r


def report_lines(rep):
    """Russian lines for the launcher: start / mined / found / spent (derived) / passed remainder."""
    out = []
    for k, name in (('minerals', 'Минералы'), ('gas', 'Газ')):
        r = rep[k]
        out.append('%s: стартовый запас %d, добыто %d, найдено %d, потрачено (расчётно: старт + добыто + найдено - остаток) %d, передано в кампанию %d' % (
            name, r['start'], r['mined'], r['found'], r['net_other_derived'], r['remainder']))
    return out


def collect(path, operation_id, launched_at, intent='fresh', bank=None):
    """After the game process exited (or read-only while it runs): the fresh journal of THIS launch. A Bank file older than the launch is stale and is
    ignored; a missing file means the map never wrote (a crash before the first write)."""
    bank = bank or bank_file()
    if not os.path.exists(bank) or os.path.getmtime(bank) + 1.0 < launched_at:
        return {'fresh': False, 'records': [], 'proposals': [], 'held': []}
    records, proposals = parse_journal(journal_rows(bank))
    records = [r for r in records if r['op'] == operation_id]
    proposals = [p for p in proposals if p['op'] == operation_id]
    s, held = observe(path, records, intent)
    return {'fresh': True, 'records': records, 'proposals': proposals, 'held': held}
