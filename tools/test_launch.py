"""Automatic test launches of StarCraft II (developer mode; the Owner's normal GUI / CLI launch never uses this).

Rules (see CLAUDE.md): the test game runs in a small ordinary window on the second monitor (the primary one only when
there is no second monitor, and that is reported), without sound (only the audio sessions of our own process), without
Always on Top and without forcing the focus; only the process started here is ever touched. Nothing in the Owner's
permanent game settings changes: everything is a parameter of this one launch plus the control of this one window.

  python tools/test_launch.py --mission traynor02 --preset tactical_dev --seconds 100 [--keep] [--width 1024 --height 768]
"""
import argparse
import ctypes
import glob
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import monitors  # noqa: E402

DOCS = os.path.join(os.path.expanduser('~'), 'Documents', 'StarCraft II')
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010


def sc2_pids():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq SC2_x64.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    return [int(l.split(',')[1].strip('"')) for l in out.splitlines() if 'SC2_x64.exe' in l]


def windows_of(pid):
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 200:
                found.append((hwnd, r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(cb, 0)
    return found


def test_command(adapter, cfg, preset, x, y, w, h):
    """The launch command of this one test game: ordinary window of the given size at the given place."""
    command, dest = build.launch_command(adapter, cfg, preset)
    command = command.replace('-displaymode 2', '-displaymode 0 -windowwidth %d -windowheight %d -windowx %d -windowy %d' % (w, h, x, y))
    return command, dest


def wait_new_pid(before, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        now = [p for p in sc2_pids() if p not in before]
        if now:
            return now[0]
        time.sleep(0.5)
    return None


def place_window(pid, rect, timeout=60):
    """Wait for the window of our process; move it (without activating it) only if it is not where it belongs."""
    user32 = ctypes.windll.user32
    x, y, w, h = rect
    end = time.time() + timeout
    while time.time() < end:
        wins = windows_of(pid)
        if wins:
            hwnd, l, t, r, b = max(wins, key=lambda e: (e[3] - e[1]) * (e[4] - e[2]))
            moved = False
            if abs(l - x) > 40 or abs(t - y) > 80:
                user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)
                moved = True
                time.sleep(0.5)
                r2 = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r2))
                l, t, r, b = r2.left, r2.top, r2.right, r2.bottom
            return {'hwnd': hwnd, 'pid': pid, 'rect': (l, t, r, b), 'moved_after_start': moved}
        time.sleep(0.5)
    return None


def inside(rect, mon):
    l, t, r, b = rect
    wl, wt, wr, wb = mon.work
    return l >= wl and t >= wt and r <= wr and b <= wb


def grab_window(win, path):
    """Screenshot of exactly the area of our test window - only if that window is what is on screen there (nothing else is captured)."""
    from PIL import ImageGrab
    monitors.list_monitors()  # DPI awareness first: the rectangle must be in physical pixels
    user32 = ctypes.windll.user32
    l, t, r, b = win['rect']
    root = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT((l + r) // 2, (t + b) // 2)), 2)
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(root, ctypes.byref(owner))
    if owner.value != win['pid']:
        print('screenshot skipped: another window (process %d) covers the test window' % owner.value)
        return False
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save(path)
    return True


def run(mission, preset, seconds, keep=False, width=1024, height=768, shot=None, shot_at=20):
    report = {}
    if sc2_pids():
        print('StarCraft II is already running (not ours): the test launch is refused, the game is not touched')
        return 9, report
    mons = monitors.list_monitors()
    mon, second = monitors.test_monitor(mons)
    x, y, w, h = monitors.test_window_rect(mon, width, height)
    report['monitor'] = repr(mon)
    report['second_monitor'] = second
    args = argparse.Namespace(mission=mission, preset=preset, source=None, multiplier=None, diag=False, print_only=False, start=True)
    rc = build.prepare(args)
    if rc != 0:
        print('prepare failed', rc)
        return rc, report
    for f in glob.glob(os.path.join(DOCS, 'Banks', '**', 'GhostOpsDevTac*'), recursive=True):
        os.remove(f)
    t0 = time.time()
    adapter, cfg, name = build.context(args)
    command, _ = test_command(adapter, cfg, name, x, y, w, h)
    before = sc2_pids()
    build.start_detached(command)
    pid = wait_new_pid(before)
    if pid is None:
        print('the test game did not start')
        return 8, report
    report['pid'] = pid
    # sound off: only our own process
    mute = subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'mute_process.ps1'),
                             '-ProcessId', str(pid), '-Seconds', str(max(30, seconds))], stdout=subprocess.PIPE, text=True)
    win = place_window(pid, (x, y, w, h))
    report['window'] = win
    report['window_fits_work_area'] = bool(win and inside(win['rect'], mon))
    print('test game pid %d on %s (%s); window %s; fits the work area: %s' % (
        pid, mon.device, 'second monitor' if second else 'PRIMARY: there is no second monitor', win and win['rect'], report['window_fits_work_area']))
    if shot and win:
        time.sleep(max(0, shot_at - (time.time() - t0)))
        print('screenshot:', shot if grab_window(win, shot) else 'none')
    time.sleep(max(0, seconds - (time.time() - t0)))
    try:
        mute.wait(timeout=5)
    except subprocess.TimeoutExpired:
        mute.terminate()
    report['mute'] = (mute.stdout.read() or '').strip()
    print('audio:', report['mute'])
    for f in glob.glob(os.path.join(DOCS, 'GameLogs', '*ScriptError*.txt')):
        if os.path.getmtime(f) >= t0 - 5:
            text = open(f, encoding='utf-8-sig', errors='replace').read()
            ours = [ln for ln in text.splitlines() if re.search(r'compile|GhostOps|Script load failed', ln)]
            print('ScriptError:', os.path.basename(f), 'lines about our code/compile:', ours[:5])
    if not keep:
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
        print('closed our own test game, pid', pid)
        if str(preset or '').endswith('_dev'):  # a developer map never stays in the Owner's map list
            time.sleep(2)
            build.uninstall_key(build.key_for(adapter, name), 'dev map')
    return 0, report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mission', default='traynor02')
    p.add_argument('--preset', default='tactical_dev')
    p.add_argument('--seconds', type=int, default=100)
    p.add_argument('--keep', action='store_true')
    p.add_argument('--width', type=int, default=1024)
    p.add_argument('--height', type=int, default=768)
    p.add_argument('--shot', help='save one screenshot of the test window (only if nothing covers it)')
    p.add_argument('--shot-at', type=int, default=20, help='seconds after the start')
    a = p.parse_args(argv)
    rc, _ = run(a.mission, a.preset, a.seconds, a.keep, a.width, a.height, a.shot, a.shot_at)
    return rc


if __name__ == '__main__':
    sys.exit(main())
