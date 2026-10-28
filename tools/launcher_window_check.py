"""Real-window check of the launcher screen (no game, no build, nothing installed): isolated settings / campaign file / Workshop folder and a fake backend that only records the
start. The window of the Owner is never touched: this window is placed on the second monitor (or the primary one when there is none) without activation, and only OUR window is captured
(PrintWindow).

Usage: python tools/launcher_window_check.py OUTDIR [--scale 1.5]   (prints PASS / FAIL lines; PNGs of the window go to OUTDIR)
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(argv):
    outdir = argv[0]
    scale = float(argv[argv.index('--scale') + 1]) if '--scale' in argv else 1.0
    tmp = tempfile.mkdtemp(prefix='launcher_check_')
    os.environ['GHOSTOPS_WORKSHOP_DIR'] = os.path.join(tmp, 'variants')
    os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(tmp, 'campaign.json')
    os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(tmp, 'no_lines')
    os.makedirs(outdir, exist_ok=True)
    import gui_launcher
    import launcher_core as core
    import monitors
    import campaign
    if not gui_launcher.ensure_dependencies():
        print('FAIL customtkinter missing')
        return 2
    # an isolated campaign with one paid operation of an EARLIER version of Zero Hour (the new recommended version must not replace it)
    st = campaign.new_campaign(1000, 200)
    st['operations']['OP0001'] = {'mission': 'traynor03', 'profile': 'defence_r5', 'state': 'paid', 'cost': {}, 'handed': {}, 'attempts': {}}
    with open(os.environ['GHOSTOPS_CAMPAIGN_FILE'], 'w', encoding='utf-8') as f:
        json.dump(st, f)

    ctk, App = gui_launcher.build_app()
    if scale != 1.0:
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
    res = []

    def check(name, ok, extra=''):
        res.append(bool(ok))
        print(('PASS ' if ok else 'FAIL ') + name + (' | ' + str(extra) if extra else ''))

    class FakeBackend:
        def __init__(self):
            self.prepared, self.started = [], []

        def configure(self, game_dir):
            pass

        def sc2_running(self):
            return False

        def prepare(self, mission, preset, progress):
            self.prepared.append((mission, preset))
            progress('check')
            return 0

        def start(self, mission, preset):
            self.started.append((mission, preset))
            return 0

        def status(self, mission, preset, game_dir=None):
            return 'needs_build' if (mission, preset) == ('thanson02', 'epidemic_free_r8') else 'ready'

        def build_hash(self, mission, preset):
            return 'abc123def456'

    backend = FakeBackend()
    launcher = core.Launcher(settings=core.Settings(os.path.join(tmp, 'settings.json')), backend=backend, log_fn=lambda m: None)
    launcher.settings.data['game_dir'] = r'E:\Games\StarCraft II'
    app = App(launcher=launcher)

    def pump(sec=0.4):
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def place(logical_w, logical_h, primary=False):
        """Put the window on the second monitor (primary when none, or when asked for the normal size) WITHOUT activation; sizes are logical pixels."""
        import ctypes
        ms = monitors.list_monitors()
        mon = ms[0] if primary else next((m for m in ms if not m.primary), ms[0])
        mon = next((m for m in ms if m.primary), ms[0]) if primary else mon
        k = app._get_window_scaling() or 1.0
        dpi_k = mon.scale
        w, h = int(logical_w * dpi_k), int(logical_h * dpi_k)
        hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
        ctypes.windll.user32.SetWindowPos(hwnd, 0, mon.work[0] + 20, mon.work[1] + 20, w, h, 0x0010 | 0x0004)  # SWP_NOACTIVATE | SWP_NOZORDER
        app.update()
        pump(0.5)
        return mon

    def shot(name):
        pump(0.3)
        ok = gui_launcher.grab(app, os.path.join(outdir, name + '.png'))
        check('picture of our own window: %s' % name, ok)

    def texts(widget):
        out = []
        for w in widget.winfo_children():
            t = getattr(w, 'cget', None)
            try:
                out.append(w.cget('text'))
            except Exception:  # noqa: BLE001
                pass
            out += texts(w)
        return out

    def mapped(w):
        return bool(w.winfo_ismapped())

    place(1060, 700, primary=True)  # the normal window size fits only the primary monitor; no game is running during the check
    pump(1.0)

    # 1. opening each mission shows the current version at once, the archive is closed
    for m in core.MISSIONS:
        app.select_mission(m['id'])
        pump(0.15)
        cur = core.current_revision(m['id'])
        rev = app._rev()
        check('%s: opens on the current version %d' % (m['id'], cur), rev['number'] == cur and rev['current'] and app.version_label.cget('text') == rev['label'], app.version_label.cget('text'))
        check('%s: archive closed at the start' % m['id'], not app.archive_open and not mapped(app.archive_frame), app.archive_button.cget('text'))
        check('%s: button says what it does' % m['id'], app.start_button.cget('text') in ('Запустить тест · версия %d' % cur, 'Открыть кампанию'), app.start_button.cget('text'))
        check('%s: composition and changes belong to the selected profile' % m['id'], app.changes_label.cget('text').startswith('Изменения:') and (app.comp_label.cget('text').startswith('Состав:') or app._sel()['mode'] == 'campaign'))

    # 2. the build state is read, the redraw never builds
    app.select_mission('thanson02')
    pump(0.6)
    check('thanson02: current version not built -> the window says so (no silent switch to an old one)', 'Нужно собрать' in app.build_label.cget('text') and app._rev()['current'], app.build_label.cget('text'))
    app.select_mission('thanson01')
    pump(0.6)
    check('thanson01: installed build is shown', 'Сборка установлена' in app.build_label.cget('text'), app.build_label.cget('text'))
    check('no build was started by drawing', backend.prepared == [])

    # 3. archive: opens on demand, the choice changes the summary and the real start command, back to the current
    app.select_mission('traynor03')
    pump(0.3)
    app.toggle_archive()
    pump(0.3)
    check('traynor03: the archive opens', app.archive_open and mapped(app.archive_frame) and 'Архив версий — ' in app.archive_button.cget('text'), app.archive_button.cget('text'))
    nums = [r['number'] for r in core.archive_of('traynor03')]
    check('traynor03: the archive is sorted as numbers, newest first', nums == sorted(nums, reverse=True) and 5 in nums and 0 in nums, nums)
    check('traynor03: hidden / service profiles are not in the archive', all(r['number'] in (0, 1, 2, 3, 4, 5) for r in core.archive_of('traynor03')))
    cv = app.scroll._parent_canvas
    cv.update_idletasks()
    inner = max(1, cv.bbox('all')[3])
    cv.yview_moveto(max(0.0, (app.archive_button.winfo_rooty() - app.scroll.winfo_rooty() - 10) / inner + cv.yview()[0]))  # the header of the archive at the top of the view
    pump(0.6)
    shot('02_archive_open')
    app.scroll._parent_canvas.yview_moveto(0.0)
    app.select_revision(4)
    pump(0.3)
    check('archive version 4 selected: the summary says Archive and the number', app.version_label.cget('text').startswith('Архив · версия 4'), app.version_label.cget('text'))
    check('archive version 4: the button says it launches the archive version', app.start_button.cget('text') == 'Запустить архивную версию 4', app.start_button.cget('text'))
    check('archive version 4: the build line follows the selected profile', 'Сборка' in app.build_label.cget('text') or 'Проверка' in app.build_label.cget('text'))
    app.start()
    pump(1.0)
    check('archive start: the launch command is the archive profile', backend.started and backend.started[-1] == ('traynor03', 'defence_r4_free'), backend.started)
    rec = launcher.settings.data.get('last_launch') or {}
    check('the record of the last launch says what really ran (archive, version, mode, map)', rec.get('archive') is True and rec.get('revision') == 4 and rec.get('preset') == 'defence_r4_free' and rec.get('map', '').endswith('.SC2Map'), rec)
    app.back_to_current()
    pump(0.3)
    check('back to the current version', app._rev()['current'] and app.start_button.cget('text') == 'Запустить тест · версия 6', app.start_button.cget('text'))
    app.start()
    pump(1.0)
    check('current start launches the free test of the current version', backend.started[-1] == ('traynor03', 'defence_r6_free'), backend.started[-1])

    # 4. the old paid operation keeps its own version
    check('traynor03: the paid operation of version 5 is shown with its own version', 'версии 5' in app.op_label.cget('text') and 'не подменяет' in app.op_label.cget('text'), app.op_label.cget('text'))

    # 5. mode: campaign opens the real campaign window, the free test does not look like a campaign
    app.select_mission('thanson01')
    pump(0.3)
    check('thanson01: modes are Free test and Campaign of ONE version', app._rev()['modes'] == ['free', 'campaign'] and 'Свободный тест' in app.mode_line.cget('text'))
    app.set_mode('Кампания')
    pump(0.3)
    check('campaign mode: button opens the campaign, mode line says campaign', app.start_button.cget('text') == 'Открыть кампанию' and app.mode_line.cget('text').startswith('Кампания'), app.mode_line.cget('text'))
    n_started = len(backend.started)
    app.start()
    pump(1.2)
    win = getattr(app, 'campaign_window', None)
    check('campaign mode leads into the real campaign window and starts no map', win is not None and win.winfo_exists() and len(backend.started) == n_started)
    if win is not None:
        win.destroy()
    app.set_mode('Свободный тест')
    pump(0.2)
    check('free test: the button is the test button', app.start_button.cget('text') == 'Запустить тест · версия 6')

    # 6. difficulty is a real difficulty choice, not a version
    app.select_mission('traynor01')
    pump(0.3)
    check('traynor01: difficulty chooser shows real difficulties of ONE version', core.difficulties_of(app._rev(), 'standalone') == ['Лёгкий', 'Сложный', 'Экстремальный'] and mapped(app.diff_frame))
    rev_before = app._rev()['number']
    app.set_difficulty('Сложный')
    pump(0.3)
    app.start()
    pump(1.0)
    check('difficulty changes the profile, not the version', app._rev()['number'] == rev_before and backend.started[-1] == ('traynor01', 'hard'), backend.started[-1])
    check('other missions show no difficulty chooser', (app.select_mission('thanson02'), pump(0.2), not mapped(app.diff_frame))[2])

    # 7. copy the data of the test
    app.select_mission('thanson02')
    pump(0.3)
    text = app.copy_info()
    clip = app.clipboard_get()
    check('copy: the text lands in the clipboard', clip == text)
    check('copy: mission, version, mode, profile, map, build and the last real launch', all(x in text for x in ('Эпидемия', 'Версия 8', 'Свободный тест', 'epidemic_free_r8', '.SC2Map', 'Последний запуск', 'traynor01')), text.replace('\n', ' | '))
    check('copy: the last launch is the real one (not the current choice of the window)', 'hard' in text and 'Сложность: Сложный' in text.split('Последний запуск')[1])

    # 8. details closed by default, the technical path is behind them
    check('details are closed at the start', not app.details_open and not mapped(app.details))
    app.toggle_details()
    pump(0.3)
    tech = app.tech_text.cget('text')
    check('details open: the technical profile, the map path and the build are inside', 'Профиль: epidemic_free_r8' in tech and 'Карта:' in tech and mapped(app.details), tech.replace('\n', ' | '))
    app.scroll._parent_canvas.yview_moveto(0.5)
    pump(0.4)
    shot('03_details_open')
    app.scroll._parent_canvas.yview_moveto(0.0)
    app.toggle_details()

    # 9. the current version of the screen
    app.select_mission('thanson01')
    pump(0.3)
    shot('01_current_version')

    # 10. the small work area: the start button stays reachable, text wraps, no horizontal scroll needed
    place(900, 490)
    pump(1.0)
    app.select_mission('traynor03')
    app.toggle_archive()
    pump(0.6)
    app.update_idletasks()
    sb = app.start_button
    win_bottom = app.winfo_rooty() + app.winfo_height()
    check('small window: the start button is visible and inside the window', mapped(sb) and sb.winfo_rooty() + sb.winfo_height() <= win_bottom + 2 and sb.winfo_rootx() >= app.winfo_rootx(), (sb.winfo_rooty(), sb.winfo_height(), win_bottom))
    sw = app.scroll.winfo_width()
    widest = 0
    for lb, margin in app.wrap_labels:
        try:
            if lb.winfo_exists() and lb.winfo_ismapped():
                widest = max(widest, lb.winfo_rootx() + lb.winfo_width() - app.scroll.winfo_rootx())
        except Exception:  # noqa: BLE001
            pass
    check('small window: no label sticks out to the right (no horizontal scroll for the main actions)', widest <= sw + 4, (widest, sw))
    shot('04_small_window')
    check('small window: the full version label is readable (wraps instead of being cut)', 'Версия' in app.version_label.cget('text') and int(app.version_label.cget('wraplength')) > 0)
    app.destroy()
    ok = all(res)
    print('ALL PASS' if ok else 'SOME FAILED', '(%d checks)' % len(res))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
