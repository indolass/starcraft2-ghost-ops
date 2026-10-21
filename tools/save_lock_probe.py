"""Comparative probe of the "save is locked" state of the game menu (PREPARED, NOT RUN: it starts a test game, so it refuses while any StarCraft II runs).

What it answers: is the padlock between "Save" and "Load" in the F10 menu (a) on our installed map, (b) on an UNMODIFIED Blizzard mission map
(tmp/source/TRaynor02.SC2Map, copied to Maps\\GhostOpsProbe for the run and removed afterwards). Same game binary, same launch chain, same window.
  - both locked  -> the state is the game/licence side (not our map content);
  - only ours locked -> something in our map is the cause and the next step is a bisect of the map content.
It only opens the menu and takes a screenshot of OUR window; it never saves, never touches saves/Banks/campaign.json, never closes a game that is not ours.

  python tools/save_lock_probe.py            # runs both maps, writes tmp/ce0/save_lock_probe.json
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import monitors  # noqa: E402
import sc2_ui  # noqa: E402
import test_launch  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'tmp', 'ce0')
PROBE_DIR = os.path.join(build.SC2_DIR, 'Maps', 'GhostOpsProbe')
LOCK_BOX = (355, 305, 700, 355)   # between the Save and Load buttons of the 1050x839 window picture (primary-monitor layout)


def lock_visible(img):
    """The padlock is a small bright blue glyph in the middle of that box: count bright bluish pixels around the centre."""
    c = img.convert('RGB').crop((LOCK_BOX[0] + 150, LOCK_BOX[1], LOCK_BOX[0] + 200, LOCK_BOX[3]))
    n = 0
    for r, g, b in c.getdata():
        if b > 190 and b > r + 40:
            n += 1
    return n


def run_one(name, map_path):
    before = test_launch.sc2_pids()
    mons = monitors.list_monitors()
    mon, _ = monitors.test_monitor(mons)
    x, y, w, h = monitors.test_window_rect(mon, 1024, 768)
    cmd = ('"%s" -run "%s" ' + os.environ.get('PROBE_EXTRA', '') + ' -displaymode 0 -windowwidth %d -windowheight %d -windowx %d -windowy %d') % (
        os.path.join(build.SC2_DIR, 'Support64', 'SC2Switcher_x64.exe'), map_path, w, h, x, y)
    build.start_detached(cmd)
    pid = test_launch.wait_new_pid(before)
    if pid is None:
        return {'map': name, 'error': 'game did not start'}
    subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'mute_process.ps1'),
                      '-ProcessId', str(pid), '-Seconds', '120'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(45)
    sc2_ui.key(pid, ['F10'], 1.5)
    shot = os.path.join(OUT, 'save_lock_probe_%s.png' % name)
    sc2_ui.shot(pid, shot)
    sc2_ui.key(pid, ['ESC'], 0.5)
    import hashlib
    res = {'map': name, 'path': map_path, 'sha256': hashlib.sha256(open(map_path, 'rb').read()).hexdigest(), 'command': cmd, 'pid': pid,
           'exe': subprocess.run(['powershell', '-NoProfile', '-Command', '(Get-Process -Id %d).Path' % pid], capture_output=True, text=True).stdout.strip(),
           'lock_pixels': lock_visible(Image.open(shot)), 'screenshot': shot}
    subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)   # OUR pid only
    time.sleep(3)
    return res


def main():
    if test_launch.sc2_pids():
        print('StarCraft II is running (not ours): refused, nothing is touched')
        return 9
    os.makedirs(OUT, exist_ok=True)
    results = []
    extra = [a.split('=', 1) for a in sys.argv[1:] if '=' in a]
    for nm, pth in extra:
        results.append(run_one(nm, pth))
    if extra:
        json.dump(results, open(os.path.join(OUT, 'save_lock_probe.json'), 'w'), indent=2)
        print(json.dumps(results, indent=2))
        return 0
    ours = os.path.join(build.SC2_DIR, 'Maps', 'GhostOps', 'GhostOps_TRaynor02_r2_tactical.SC2Map')
    results.append(run_one('ours_r2_tactical', ours))
    os.makedirs(PROBE_DIR, exist_ok=True)
    try:
        orig = os.path.join(PROBE_DIR, 'ProbeTRaynor02.SC2Map')
        shutil.copyfile(os.path.join(ROOT, 'tmp', 'source', 'TRaynor02.SC2Map'), orig)
        results.append(run_one('blizzard_original_TRaynor02', orig))
    finally:
        shutil.rmtree(PROBE_DIR, ignore_errors=True)
    json.dump(results, open(os.path.join(OUT, 'save_lock_probe.json'), 'w'), indent=2)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
