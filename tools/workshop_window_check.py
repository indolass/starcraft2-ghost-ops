"""Real-window check of the Mission Workshop (no game, no build, nothing installed): isolated variant folder and launcher settings, a fake start backend.
Usage: python tools/workshop_window_check.py OUTDIR   (prints PASS/FAIL lines; PNGs of exactly the Workshop window are saved to OUTDIR)"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(outdir):
    tmp = tempfile.mkdtemp(prefix='wk_check_')
    os.environ['GHOSTOPS_WORKSHOP_DIR'] = os.path.join(tmp, 'variants')
    os.makedirs(outdir, exist_ok=True)
    import gui_launcher
    import launcher_core as core
    import workshop
    if not gui_launcher.ensure_dependencies():
        print('FAIL customtkinter missing')
        return 2
    ctk, App = gui_launcher.build_app()
    res = []

    def check(name, ok, extra=''):
        res.append(bool(ok))
        print(('PASS ' if ok else 'FAIL ') + name + (' | ' + str(extra) if extra else ''))

    launcher = core.Launcher(settings=core.Settings(os.path.join(tmp, 'settings.json')))
    app = App(launcher=launcher)
    app.update()

    def pump(sec=0.4):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def shot(win, name):
        """PrintWindow of OUR window only (never a screen area: a DPI-unaware grab captured the Owner's browser once)."""
        import ctypes
        from ctypes import wintypes as wt
        from PIL import Image
        pump(0.3)
        user32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        hdc = user32.GetWindowDC(hwnd)
        mdc = gdi.CreateCompatibleDC(hdc)
        bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
        gdi.SelectObject(mdc, bmp)
        ok = user32.PrintWindow(hwnd, mdc, 2)

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
        if ok:
            Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB').save(os.path.join(outdir, name + '.png'))

    class FakeBackend:
        started = []

        def sc2_running(self):
            return False

        def start(self, variant):
            self.started.append(variant['id'])
            return 0

    app.select_mission('thanson01')
    pump()
    win = app.open_workshop()
    check('workshop window opens for Evacuation', win is not None)
    pump()
    fb = FakeBackend()
    win.backend = fb
    win.geometry('+40+40')
    v = win.create_variant('Проверка окна')
    pump()
    check('variant created from a free profile', v['changes'] == {} and v['mission'] == 'thanson01')
    shot(win, '01_new_variant')
    # sections
    for sid, _ in getattr(workshop, 'SECTIONS', []):
        win.pick_section(sid)
        pump(0.15)
    win.pick_section('ghosts')
    pump()
    check('edit by value', win.set_value('snipe_cd', '2.0') and workshop.effective_cfg(win.variant)['ghost_tuning']['snipe']['cooldown'] == 2.0)
    win._arrow('snipe_cd', +1)
    pump()
    check('edit by arrow', abs(workshop.effective_cfg(win.variant)['ghost_tuning']['snipe']['cooldown'] - (2.0 + workshop.BY_ID['snipe_cd'].step)) < 1e-6)
    win._reset('snipe_cd')
    check('reset to base', 'snipe_cd' not in win.variant['changes'])
    win.set_value('snipe_cd', '1.0')
    ok = win.set_value('snipe_dmg', 'abc')
    pump()
    check('unreadable value is refused, build blocked', ok is False and win.current_status() == 'invalid', win.status_label.cget('text'))
    shot(win, '02_invalid_value')
    win.set_value('snipe_dmg', '300')
    check('valid value clears the block', win.current_status() in ('draft', 'needs_build'))
    win.save_variant()
    vid = win.variant['id']
    shot(win, '03_saved')
    win.destroy()
    pump()
    app.workshop_window = None
    win2 = app.open_workshop()
    pump()
    check('reopen restores the saved variant', win2.variant is not None and win2.variant['id'] == vid and win2.variant['changes'].get('snipe_cd') == 1.0, win2.variant and win2.variant['changes'])
    win2.backend = fb
    # second variant and switch between them
    v2 = win2.create_variant('Второй')
    check('second variant lives in the same mission card', len(workshop.list_variants('thanson01')) == 2)
    win2._pick_variant(win2._label(workshop.load('thanson01', vid)))
    check('switching variants keeps their own changes', win2.variant['id'] == vid and win2.variant['changes'].get('snipe_cd') == 1.0 and v2['changes'] == {})
    # the launcher shows the own variants of the mission
    app._refresh()
    pump()
    check('launcher card counts own variants', 'Свои варианты (Мастерская): 2' in app.description_label.cget('text'))
    # resize: the layout must stay usable; buttons stay reachable
    for w, h in ((1000, 620), (1040, 600), (1400, 900)):
        win2.geometry('%dx%d' % (w, h))
        pump(0.6)
        win2.update_idletasks()
        for btn in (win2.run_button,):
            bottom = btn.winfo_rooty() + btn.winfo_height()
            top_win = win2.winfo_rooty()
            check('run button inside window at %dx%d' % (w, h), top_win <= btn.winfo_rooty() and bottom <= top_win + win2.winfo_height() + 2, (btn.winfo_rooty() - top_win, win2.winfo_height()))
        shot(win2, '04_size_%dx%d' % (w, h))
    # an unusually strong value is allowed (warning), an impossible one blocks
    win2.set_value('snipe_dmg', '900')
    errs, warns = workshop.validate(win2.variant)
    check('strong value only warns', not errs and warns, warns)
    shot(win2, '05_strong_warning')
    app.destroy()
    print('RESULT %d/%d' % (sum(res), len(res)))
    return 0 if all(res) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join('tmp', 'workshop_check')))
