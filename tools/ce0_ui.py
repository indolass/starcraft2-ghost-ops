"""CE-0 developer helper: the in-game menu flows (save, load) of OUR test game, by posted window messages (see sc2_ui.py).
Coordinates are client coordinates of the 1024x768 test window. Every step is verified on a screenshot of OUR window (PrintWindow)
against reference crops in tmp/ce0 before anything is typed: a key or a click that did not open the expected dialog never leaves
text in the game (a typed name would be game hotkeys).

  python tools/ce0_ui.py save NAME          # F10 -> Save -> name -> Enter; waits for the new .SC2Save
  python tools/ce0_ui.py load [INDEX]       # F10 -> Load -> item INDEX of the list (0 = the newest save) -> Load
  python tools/ce0_ui.py window             # check / restore size and place of the window (never maximised, never moved to another monitor)
"""
import ctypes
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc2_ui  # noqa: E402
import test_launch  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

ROOT = os.path.dirname(HERE)
TMP = os.path.join(ROOT, 'tmp', 'ce0')
SAVE_BTN, LOAD_BTN = (447, 274), (570, 274)   # layout of the 1050x839 window picture (primary-monitor fallback)
FIRST_ITEM, LOAD_OK = (352, 275), (912, 655)
user32 = ctypes.windll.user32


def session():
    return json.load(open(os.path.join(TMP, 'session.json')))


def ensure_window():
    st = session()
    wins = test_launch.windows_of(st['pid'])
    if not wins:
        raise SystemExit('no window of our test game')
    h, l, t, r, b = max(wins, key=lambda e: (e[3] - e[1]) * (e[4] - e[2]))
    x, y, x2, y2 = st['window']
    if user32.IsZoomed(h):
        user32.PostMessageW(h, 0x112, 0xF120, 0)  # SC_RESTORE
        time.sleep(1.5)
    if abs(l - x) > 40 or abs(t - y) > 80 or abs((r - l) - (x2 - x)) > 40:
        user32.SetWindowPos(h, 0, x, y, x2 - x, y2 - y, 0x0004 | 0x0010)
        time.sleep(0.8)
        print('window put back to', (x, y, x2, y2))
    return st['pid']


def shot_img(pid, name='cur.png'):
    path = os.path.join(TMP, name)
    sc2_ui.shot(pid, path)
    return Image.open(path).convert('RGB')


def matches(img, ref_name, box, tol=14.0):
    ref = Image.open(os.path.join(TMP, ref_name)).convert('RGB')
    diff = ImageChops.difference(img.crop(box), ref)
    return sum(ImageStat.Stat(diff).mean) / 3.0 < tol


def wait_for(pid, ref, box, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        if matches(shot_img(pid), ref, box):
            return True
        time.sleep(0.6)
    return False


def newest_saves():
    return {f: os.path.getmtime(f) for f in glob.glob(os.path.join(test_launch.DOCS, 'Saves', '**', '*.SC2Save'), recursive=True)}


def save(name):
    pid = ensure_window()
    before = newest_saves()
    sc2_ui.key(pid, ['F10'], 1.0)
    sc2_ui.click(pid, *SAVE_BTN)
    if not wait_for(pid, 'ref_save_header.png', (80, 195, 290, 235)):
        print('SAVE DIALOG NOT SHOWN: nothing typed')
        sc2_ui.key(pid, ['ESC'], 0.5)
        return 1
    sc2_ui.key(pid, ['BACK'], 0.2)
    sc2_ui.type_text(pid, name)
    time.sleep(0.5)
    sc2_ui.key(pid, ['ENTER'], 1.5)
    end = time.time() + 10
    while time.time() < end:
        new = [f for f, m in newest_saves().items() if f not in before or m != before[f]]
        if new:
            print('saved:', new[0])
            return 0
        time.sleep(0.5)
    print('NO NEW SAVE FILE')
    return 2


def load(index=0):
    pid = ensure_window()
    sc2_ui.key(pid, ['F10'], 1.0)
    sc2_ui.click(pid, *LOAD_BTN)
    if not wait_for(pid, 'ref_load_header.png', (80, 195, 290, 235)):
        print('LOAD DIALOG NOT SHOWN: nothing clicked further')
        sc2_ui.key(pid, ['ESC'], 0.5)
        return 1
    sc2_ui.click(pid, FIRST_ITEM[0], FIRST_ITEM[1] + int(22.5 * index))
    time.sleep(1.0)
    sc2_ui.click(pid, *LOAD_OK)
    return 0


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'save':
        sys.exit(save(sys.argv[2]))
    elif c == 'load':
        sys.exit(load(int(sys.argv[2]) if len(sys.argv) > 2 else 0))
    elif c == 'window':
        ensure_window()
