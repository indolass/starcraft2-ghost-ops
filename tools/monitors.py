"""Physical monitor geometry (per-monitor DPI aware) for the automatic test launches of StarCraft II.

The coordinates are physical pixels of the virtual desktop; a monitor to the left of / above the primary one has
negative coordinates. Nothing here is hard coded: the layout is read from Windows every time.
"""
import ctypes
from ctypes import wintypes


class Monitor:
    def __init__(self, handle, left, top, right, bottom, wleft, wtop, wright, wbottom, primary, dpi, device):
        self.handle, self.primary, self.dpi, self.device = handle, primary, dpi, device
        self.left, self.top, self.right, self.bottom = left, top, right, bottom
        self.work = (wleft, wtop, wright, wbottom)

    @property
    def scale(self):
        return self.dpi / 96.0

    def __repr__(self):
        return 'Monitor(%s primary=%s bounds=(%d,%d,%d,%d) work=%s dpi=%d)' % (
            self.device, self.primary, self.left, self.top, self.right, self.bottom, self.work, self.dpi)


class _MonitorInfoEx(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                ('dwFlags', wintypes.DWORD), ('szDevice', wintypes.WCHAR * 32)]


def list_monitors():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per monitor: physical pixels
    except (OSError, AttributeError):
        ctypes.windll.user32.SetProcessDPIAware()
    out = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(hmon, hdc, rect, lparam):
        info = _MonitorInfoEx()
        info.cbSize = ctypes.sizeof(_MonitorInfoEx)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
        try:
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
        except (OSError, AttributeError):
            pass
        m, w = info.rcMonitor, info.rcWork
        out.append(Monitor(hmon, m.left, m.top, m.right, m.bottom, w.left, w.top, w.right, w.bottom,
                           bool(info.dwFlags & 1), dx.value, info.szDevice))
        return True

    user32.EnumDisplayMonitors(None, None, cb, 0)
    return out


def test_monitor(monitors=None):
    """The monitor for automatic test games: the first one that is not the primary; the primary if there is only one.
    Returns (monitor, is_secondary)."""
    mons = monitors or list_monitors()
    for m in mons:
        if not m.primary:
            return m, True
    return mons[0], False


def test_window_rect(monitor, width=1024, height=768, margin=8):
    """(x, y, w, h) of a window that fits the work area of the monitor completely; shrunk (4:3 kept) if it does not."""
    wl, wt, wr, wb = monitor.work
    aw, ah = wr - wl - 2 * margin, wb - wt - 2 * margin - 40  # 40: caption bar of a normal window
    w, h = width, height
    if w > aw or h > ah:
        k = min(aw / float(w), ah / float(h))
        w = int(width * k) // 32 * 32
        h = w * height // width
    x = wl + (wr - wl - w) // 2
    y = wt + max(margin, (wb - wt - h - 40) // 2)
    return x, y, w, h


if __name__ == '__main__':
    mons = list_monitors()
    for m in mons:
        print(m)
    mon, second = test_monitor(mons)
    print('test monitor:', mon.device, 'secondary' if second else 'PRIMARY (no second monitor)', test_window_rect(mon))
