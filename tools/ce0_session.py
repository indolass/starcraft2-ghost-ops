"""CE-0 developer session helper (development only; never part of a playable build, never used by the launcher).

Starts ONE test game of a hidden ce0_dev profile under the rules of CLAUDE.md (small window on the second monitor, only our own process
muted, no focus forcing, never touches a game that is not ours) and keeps it alive between commands, so that real saves, loads, quits
and restarts can be checked step by step. State of the session: tmp/ce0/session.json.

  python tools/ce0_session.py start --mission traynor02 [--preset ce0_dev] [--width 1024 --height 768]
  python tools/ce0_session.py cmd "snap before"          # types a chat command into OUR test window (Enter, text, Enter)
  python tools/ce0_session.py journal [--since N] [--section j|r] [--grep TEXT]
  python tools/ce0_session.py key F10 ENTER ...          # posted keys (names as in sc2_ui.py)
  python tools/ce0_session.py click X Y                  # client coordinates
  python tools/ce0_session.py shot FILE
  python tools/ce0_session.py saves                      # the game's save files (name, size, time, sha256)
  python tools/ce0_session.py scripterror                # new ScriptError lines about our code / compile
  python tools/ce0_session.py stop [--hard]              # close OUR game (taskkill of the session pid) and uninstall the dev map
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import monitors  # noqa: E402
import sc2_ui  # noqa: E402
import test_launch  # noqa: E402

ROOT = build.ROOT
DOCS = test_launch.DOCS
STATE = os.path.join(ROOT, 'tmp', 'ce0', 'session.json')
BANKS = os.path.join(DOCS, 'Banks')


def load_state():
    if not os.path.exists(STATE):
        raise SystemExit('no CE-0 session (run start first)')
    return json.load(open(STATE))


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, 'w'), indent=2)


def bank_files(name='GhostOpsCe0'):
    return sorted(glob.glob(os.path.join(BANKS, '**', name + '.SC2Bank'), recursive=True))


def read_bank(path):
    """{section: {key: string}} of an SC2Bank file (the signature is not checked here)."""
    out = {}
    root = ET.parse(path).getroot()
    for sec in root.findall('Section'):
        d = out.setdefault(sec.get('name'), {})
        for key in sec.findall('Key'):
            v = key.find('Value')
            if v is not None:
                d[key.get('name')] = v.get('string') or v.get('int') or v.get('fixed') or v.get('flag') or ''
    return out


def journal(section='j', since=0, name='GhostOpsCe0'):
    files = bank_files(name)
    if not files:
        return []
    b = read_bank(files[0])
    rows = []
    for k, v in b.get(section, {}).items():
        m = re.match(r'(\d+)\|(.*)', v)
        if m and int(m.group(1)) > since:
            rows.append((int(m.group(1)), m.group(2)))
    return sorted(rows)


def cmd_start(a):
    if test_launch.sc2_pids():
        print('StarCraft II is already running (not ours): refused, the game is not touched')
        return 9
    mons = monitors.list_monitors()
    mon, second = monitors.test_monitor(mons)
    x, y, w, h = monitors.test_window_rect(mon, a.width, a.height)
    args = argparse.Namespace(mission=a.mission, preset=a.preset, source=None, multiplier=None, diag=False, print_only=False, start=True, plan=a.plan)
    if not a.no_prepare:
        rc = build.prepare(args)
        if rc != 0:
            print('prepare failed', rc)
            return rc
    if not a.keep_bank:
        for f in bank_files():
            os.remove(f)
    adapter, cfg, name = build.context(args)
    command, dest = test_launch.test_command(adapter, cfg, name, x, y, w, h)
    if a.save:
        command = '"%s" -run "%s"' % (os.path.join(build.SC2_DIR, 'Support64', 'SC2Switcher_x64.exe'), a.save)
        command += ' -displaymode 0 -windowwidth %d -windowheight %d -windowx %d -windowy %d' % (w, h, x, y)
    before = test_launch.sc2_pids()
    t0 = time.time()
    build.start_detached(command)
    pid = test_launch.wait_new_pid(before)
    if pid is None:
        print('the test game did not start')
        return 8
    subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'mute_process.ps1'),
                      '-ProcessId', str(pid), '-Seconds', str(a.mute_seconds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    win = test_launch.place_window(pid, (x, y, w, h))
    st = {'pid': pid, 'mission': a.mission, 'preset': name, 'started': t0, 'map': dest, 'second_monitor': second,
          'window': win and win['rect'], 'command': command, 'operation': adapter.get('_op')}
    save_state(st)
    print('test game pid %d on %s (%s); window %s' % (pid, mon.device, 'second monitor' if second else 'PRIMARY: no second monitor', win and win['rect']))
    return 0


def cmd_cmd(a):
    st = load_state()
    sc2_ui.key(st['pid'], ['ENTER'], 0.4)
    sc2_ui.type_text(st['pid'], a.text)
    time.sleep(0.3)
    sc2_ui.key(st['pid'], ['ENTER'], 0.4)
    time.sleep(a.wait)
    rows = journal('j', a.since)
    for n, t in rows[-a.tail:]:
        print(n, t)
    return 0


def cmd_journal(a):
    for n, t in journal(a.section, a.since):
        if not a.grep or a.grep in t:
            print(n, t)
    return 0


def cmd_key(a):
    sc2_ui.key(load_state()['pid'], a.keys, 0.5)
    return 0


def cmd_click(a):
    sc2_ui.click(load_state()['pid'], a.x, a.y)
    return 0


def cmd_shot(a):
    print('shot', 'ok' if sc2_ui.shot(load_state()['pid'], a.file) else 'failed')
    return 0


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def cmd_saves(a):
    for f in sorted(glob.glob(os.path.join(DOCS, 'Saves', '**', '*.SC2Save'), recursive=True), key=os.path.getmtime):
        print('%s  %9d  %s  %s' % (time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(f))), os.path.getsize(f), sha(f)[:12], f))
    return 0


def cmd_scripterror(a):
    t0 = load_state()['started']
    for f in glob.glob(os.path.join(DOCS, 'GameLogs', '*ScriptError*.txt')):
        if os.path.getmtime(f) >= t0 - 5:
            text = open(f, encoding='utf-8-sig', errors='replace').read()
            ours = [ln for ln in text.splitlines() if re.search(r'compile|GhostOps|Script load failed|Ce0|c0', ln)]
            print(os.path.basename(f), 'lines about our code / compile:', ours[:8] or 'none')
    return 0


def cmd_stop(a):
    st = load_state()
    pids = test_launch.sc2_pids()
    if st['pid'] in pids:
        subprocess.run(['taskkill', '/PID', str(st['pid']), '/T', '/F'], capture_output=True)
        print('closed our own test game, pid', st['pid'])
    else:
        print('our test game is not running any more')
    if not a.keep_map:
        time.sleep(2)
        adapter = build.load_adapter(st['mission'])
        if st.get('operation'):
            adapter['_op'] = st['operation']
        build.uninstall_key(build.key_for(adapter, st['preset']), 'dev map')
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='c', required=True)
    s = sub.add_parser('start')
    s.add_argument('--mission', default='traynor02')
    s.add_argument('--preset', default='ce0_dev')
    s.add_argument('--width', type=int, default=1024)
    s.add_argument('--height', type=int, default=768)
    s.add_argument('--keep-bank', action='store_true')
    s.add_argument('--save', help='start by opening this .SC2Save instead of the map')
    s.add_argument('--no-prepare', action='store_true', help='do not build / install (the installed map file stays exactly as it is)')
    s.add_argument('--plan', help='an operation plan JSON (builds the unique map file of that operation)')
    s.add_argument('--mute-seconds', type=int, default=3000)
    s.set_defaults(f=cmd_start)
    s = sub.add_parser('cmd')
    s.add_argument('text')
    s.add_argument('--since', type=int, default=0)
    s.add_argument('--tail', type=int, default=3)
    s.add_argument('--wait', type=float, default=1.5)
    s.set_defaults(f=cmd_cmd)
    s = sub.add_parser('journal')
    s.add_argument('--section', default='j')
    s.add_argument('--since', type=int, default=0)
    s.add_argument('--grep')
    s.set_defaults(f=cmd_journal)
    s = sub.add_parser('key')
    s.add_argument('keys', nargs='+')
    s.set_defaults(f=cmd_key)
    s = sub.add_parser('click')
    s.add_argument('x', type=int)
    s.add_argument('y', type=int)
    s.set_defaults(f=cmd_click)
    s = sub.add_parser('shot')
    s.add_argument('file')
    s.set_defaults(f=cmd_shot)
    sub.add_parser('saves').set_defaults(f=cmd_saves)
    sub.add_parser('scripterror').set_defaults(f=cmd_scripterror)
    s = sub.add_parser('stop')
    s.add_argument('--keep-map', action='store_true')
    s.add_argument('--hard', action='store_true')
    s.set_defaults(f=cmd_stop)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == '__main__':
    sys.exit(main())
