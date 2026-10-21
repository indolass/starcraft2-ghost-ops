"""Isolation of the Owner's playable versions from development (developer tool + guards used by build.py; no game is started here).

What is protected (registry `build/owner_maps.json`, git-ignored): the map files the Owner plays or may play and load saves of - every `*.SC2Map` that was in
`Maps\\GhostOps` when `protect-all` ran and every map the Owner's normal launch started afterwards. A protected map is NEVER overwritten, replaced, renamed,
uninstalled or rebuilt by build.py (CLI, launcher and campaign window all go through it): development gets its own preset name (hidden presets such as
`defence_next`, `defence_next_dev`) and therefore its own map file. A map that a running SC2 process was started with is protected for the time it runs even
when it is not in the registry. A frozen copy of every protected map is kept in `build/owner_maps/` so a lost file can be put back (never automatically).

  python tools/isolation.py status            # the registry, the files, running maps
  python tools/isolation.py protect-all       # register every map of Maps\\GhostOps (idempotent; a changed file is reported, never re-registered silently)
  python tools/isolation.py protect NAME.SC2Map
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SC2_DIR = os.environ.get('SC2_DIR') or r'E:\Games\StarCraft II'
MAPS_DIR = os.path.join(SC2_DIR, 'Maps', 'GhostOps')
REGISTRY = os.path.join(ROOT, 'build', 'owner_maps.json')
FROZEN = os.path.join(ROOT, 'build', 'owner_maps')


class Protected(Exception):
    """A protected (Owner's) map would be changed."""


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def load():
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY, encoding='utf-8') as f:
        return json.load(f)


def _save(reg):
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    tmp = REGISTRY + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY)


def key(path):
    return os.path.basename(path).lower()


def is_protected(path):
    return key(path) in load()


def protect(path, reason='owner version'):
    """Register one installed map (and keep a frozen copy). Returns 'new', 'same' or 'changed' (a changed file is NOT re-registered)."""
    reg = load()
    k = key(path)
    sha = _sha(path)
    if k in reg:
        return 'same' if reg[k]['sha256'] == sha else 'changed'
    os.makedirs(FROZEN, exist_ok=True)
    frozen = os.path.join(FROZEN, '%s.%s' % (os.path.basename(path), sha[:12]))
    if not os.path.exists(frozen):
        shutil.copyfile(path, frozen)
    reg[k] = {'file': os.path.basename(path), 'sha256': sha, 'reason': reason, 'registered': time.strftime('%Y-%m-%d %H:%M:%S'), 'frozen_copy': frozen}
    _save(reg)
    return 'new'


def protect_all():
    out = {}
    if os.path.isdir(MAPS_DIR):
        for n in sorted(os.listdir(MAPS_DIR)):
            if n.lower().endswith('.sc2map'):
                out[n] = protect(os.path.join(MAPS_DIR, n))
    return out


def running_commands():
    """Command lines of the running SC2 processes: [(pid, creation, command line)]."""
    ps = "Get-CimInstance Win32_Process -Filter \"Name='SC2_x64.exe'\" | ForEach-Object { '{0}|{1}|{2}' -f $_.ProcessId, $_.CreationDate.ToString('o'), $_.CommandLine }"
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=30, creationflags=0x08000000).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split('|', 2)
        if len(parts) == 3 and parts[0].strip().isdigit():
            rows.append((int(parts[0]), parts[1], parts[2]))
    return rows


def running_maps():
    maps = []
    for _, _, cmd in running_commands():
        low = cmd.lower()
        i = low.find('.sc2map')
        if i >= 0:
            j = low.rfind('"', 0, i)
            maps.append(cmd[j + 1:i + 7] if j >= 0 else cmd[:i + 7])
    return maps


def check_change(path, what='change'):
    """Raises Protected when `path` (an installed or output map) is protected or is being played right now."""
    if is_protected(path):
        raise Protected('%s is a protected version of the Owner (build/owner_maps.json): it is never %s. Build the new version under its own preset name '
                        '(for example defence_next) - it gets its own map file.' % (os.path.basename(path), what))
    for m in running_maps():
        if key(m) == key(path):
            raise Protected('%s is being played right now: it is never %s.' % (os.path.basename(path), what))


# ---- ownership of a test game: a pid alone is not enough (pids are reused); pid + creation time + the job that started it ----
OWNED = os.path.join(ROOT, 'tmp', 'testqueue', 'owned.json')


def process_created(pid):
    """Creation time (ISO text) of a running SC2_x64.exe process, or None when no such process exists."""
    for p, created, _ in running_commands():
        if p == pid:
            return created
    return None


def _owned_all():
    try:
        with open(OWNED, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def record_owned(pid, tag=''):
    """Called by the test-launch guard right after it started a test game: remembers pid + creation time (+ the queue job that asked for it)."""
    created = process_created(pid)
    rows = [r for r in _owned_all() if r.get('created') != created]
    rows.append({'pid': pid, 'created': created, 'job': os.environ.get('GHOSTOPS_QUEUE_JOB', ''), 'tag': tag, 'recorded': time.strftime('%Y-%m-%d %H:%M:%S')})
    os.makedirs(os.path.dirname(OWNED), exist_ok=True)
    with open(OWNED, 'w', encoding='utf-8') as f:
        json.dump(rows[-20:], f, indent=2)
    return created


def is_owned(pid, job=None):
    """True only when this very process (pid AND creation time) was started by our test launch (and, with `job`, for that queue job)."""
    created = process_created(pid)
    if created is None:
        return False
    return any(r['pid'] == pid and r['created'] == created and (job is None or r.get('job') == job) for r in _owned_all())


def close_owned(pid, job=None):
    """Closes a test game - only when it is verifiably ours (never by the exe name alone). Returns True when it was closed."""
    if not is_owned(pid, job):
        return False
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, creationflags=0x08000000)
    return True


def status_lines():
    reg = load()
    lines = ['registry: %s (%d protected map(s))' % (REGISTRY, len(reg))]
    for k, v in sorted(reg.items()):
        p = os.path.join(MAPS_DIR, v['file'])
        state = 'missing' if not os.path.exists(p) else ('identical' if _sha(p) == v['sha256'] else 'CHANGED ON DISK')
        lines.append('  %-48s %s  %s' % (v['file'], v['sha256'][:12], state))
    lines.append('running maps: %s' % (running_maps() or 'none'))
    return lines


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] == 'status':
        print('\n'.join(status_lines()))
        return 0
    if a[0] == 'protect-all':
        for n, r in protect_all().items():
            print('%-48s %s' % (n, r))
        return 0
    if a[0] == 'protect' and len(a) > 1:
        print(protect(os.path.join(MAPS_DIR, a[1])))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
