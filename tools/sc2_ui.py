"""Developer helper for the real save / load checks: drives ONLY the test game started by tools/test_launch.py (its PID is passed
explicitly and the window ownership is checked on every call). Keys are posted to the window; the window is raised (not activated,
not Always on Top) only for a screenshot and only if nothing foreign would be captured.

  python tools/sc2_ui.py PID shot FILE
  python tools/sc2_ui.py PID key F10 [more keys]      (posted window messages; names: F10, ESC, ENTER, UP, DOWN, TAB, A-Z, 0-9)
  python tools/sc2_ui.py PID click X Y                (client coordinates of the window)
  python tools/sc2_ui.py PID type TEXT
"""
import ctypes
import sys
import time
from ctypes import wintypes

import monitors
import test_launch  # noqa: F401  (also puts tools/ on the path)

monitors.list_monitors()  # makes this process per-monitor DPI aware: window and screen coordinates are physical pixels

user32 = ctypes.windll.user32
WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE = 0x100, 0x101, 0x102, 0x201, 0x202, 0x200
SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE = 0x2, 0x1, 0x10
HWND_TOP, HWND_BOTTOM = 0, 1
VK = {'F10': 0x79, 'ESC': 0x1B, 'ENTER': 0x0D, 'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27, 'TAB': 0x09, 'F9': 0x78, 'F11': 0x7A,
      'CTRL': 0x11, 'SPACE': 0x20, 'BACK': 0x08, 'F5': 0x74, 'F6': 0x75, 'PAUSE': 0x13}


def window(pid):
    wins = test_launch.windows_of(pid)
    if not wins:
        raise SystemExit('no window of pid %d' % pid)
    return max(wins, key=lambda e: (e[3] - e[1]) * (e[4] - e[2]))


def vk(name):
    if name.upper() in VK:
        return VK[name.upper()]
    return ord(name.upper())


def key(pid, names, pause=0.4):
    hwnd = window(pid)[0]
    for n in names:
        code = vk(n)
        user32.PostMessageW(hwnd, WM_KEYDOWN, code, 0)
        time.sleep(0.08)
        user32.PostMessageW(hwnd, WM_KEYUP, code, 0xC0000000)
        time.sleep(pause)


def click(pid, x, y):
    hwnd = window(pid)[0]
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.1)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.08)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def type_text(pid, text):
    hwnd = window(pid)[0]
    for ch in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(0.05)


def shot(pid, path):
    """Screenshot of the content of OUR window only, taken with PrintWindow (works while other windows cover it): no raising,
    no focus change, nothing of the desktop can be captured."""
    from ctypes import wintypes as wt
    from PIL import Image
    hwnd, l, t, r, b = window(pid)
    w, h = r - l, b - t
    gdi = ctypes.windll.gdi32
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT

    class BI(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                    ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD), ('x', wt.LONG), ('y', wt.LONG), ('c', wt.DWORD), ('i', wt.DWORD)]
    bi = BI()
    bi.biSize, bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = ctypes.sizeof(BI), w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    if not ok:
        return False
    Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB').save(path)
    return True


if __name__ == '__main__':
    pid, cmd, args = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
    if cmd == 'shot':
        print('shot', 'ok' if shot(pid, args[0]) else 'skipped')
    elif cmd == 'key':
        key(pid, args)
    elif cmd == 'click':
        click(pid, int(args[0]), int(args[1]))
    elif cmd == 'type':
        type_text(pid, ' '.join(args))
