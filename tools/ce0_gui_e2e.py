"""CE-1 check through the REAL campaign window (CustomTkinter widgets) with the REAL backend (build + install + start of the game); development tool, test files only.

Each phase is a separate process (= a full restart of the launcher); the campaign file is tmp/ce0/gui_campaign.json (never the Owner's %APPDATA% file).
Only the presets differ from the playable ones: the window asks for the hidden dev presets (ce0_dev / standard_dev, same prices, limits and plan) so that the probe
can write the victory of TRaynor02 without playing it to the end; the game window is the small muted test window of CLAUDE.md.

  python tools/ce0_gui_e2e.py shortage    # empty stock: the order form of TRaynor03 shows the shortage, the pay button is off, a forced call charges nothing
  python tools/ce0_gui_e2e.py start1      # click "Начать «Вне закона»": plan, unique map, game start
  (play / probe: mine, win ; close the game with ce0_session.py stop --hard --keep-map)
  python tools/ce0_gui_e2e.py accept      # the window shows the proposal after the game; click "Принять", the stock changes once
  python tools/ce0_gui_e2e.py pay         # recommended order, click "Оплатить и начать": cost and remainder shown, charged once, TRaynor03 starts
  (close the game)
  python tools/ce0_gui_e2e.py continue    # click "Продолжить сохранение": the same set starts, no second charge
  python tools/ce0_gui_e2e.py restart     # click "Перезапустить (бесплатно)": the same set and order, no second charge
  python tools/ce0_gui_e2e.py state       # the file as it is
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tmp', 'thirdparty', 'ctk'))
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402
import ce0_campaign_e2e as e2e  # noqa: E402
import customtkinter as ctk  # noqa: E402
import gui_campaign  # noqa: E402
import gui_launcher  # noqa: E402

FILE = os.path.join(ROOT, 'tmp', 'ce0', 'gui_campaign.json')
DEV = {('traynor02', 'tactical'): 'ce0_dev', ('traynor03', 'standard'): 'standard_dev'}


class DevPresetFlow(cf.CampaignFlow):
    """The window asks for the playable presets; this flow maps them to the hidden dev presets of the same mission (probe commands exist there)."""
    def start_new(self, mission, preset, order=None, progress=None):
        return super().start_new(mission, DEV.get((mission, preset), preset), order, progress)

    def quote(self, mission, preset, order):
        return super().quote(mission, DEV.get((mission, preset), preset), order)

    def order_info(self, mission, preset):
        return super().order_info(mission, DEV.get((mission, preset), preset))


def widgets(w):
    for c in w.winfo_children():
        yield c
        yield from widgets(c)


def text_of(w):
    try:
        return w.cget('text')
    except Exception:  # noqa: BLE001
        return None


def all_text(win):
    return [t for t in (text_of(w) for w in widgets(win)) if t]


def button(win, text):
    for w in widgets(win):
        if isinstance(w, ctk.CTkButton) and text_of(w) == text:
            return w
    return None


def pump(root, seconds, cond=None):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if cond and cond():
            return True
        time.sleep(0.05)
    return cond() if cond else True


def open_window():
    os.environ['GHOSTOPS_CAMPAIGN_FILE'] = FILE
    campaign.APP_DIR = os.path.join(ROOT, 'tmp', 'ce0', 'e2e_appdata')
    flow = DevPresetFlow(e2e.TestWindowBackend(), path=FILE)
    root = ctk.CTk()
    root.title('Ghost Ops campaign GUI test (host)')
    root.geometry('320x90+40+40')
    pal = dict(BG=gui_launcher.BG, PANEL=gui_launcher.PANEL, CARD=gui_launcher.CARD, LINE=gui_launcher.LINE, ACCENT=gui_launcher.ACCENT,
               ACCENT_HOVER=gui_launcher.ACCENT_HOVER, TEXT=gui_launcher.TEXT, MUTED=gui_launcher.MUTED, AMBER=gui_launcher.AMBER, RED=gui_launcher.RED,
               GREEN=gui_launcher.GREEN, FONT=gui_launcher.FONT)
    win = gui_campaign.make_window_class(ctk, pal)(root, flow=flow)
    pump(root, 1.0)
    return root, win, flow


def show(win, keys=('Запас', 'Стоимость', 'Операция', 'НЕ ХВАТАЕТ', 'Остаток', 'принят', 'игра', 'Игра', 'не ')):
    seen = set()
    for t in all_text(win):
        if t in seen:
            continue
        seen.add(t)
        if any(k in t for k in keys):
            print('  |', t.replace('\n', ' / ')[:230])


def click(root, win, label, wait=1.0):
    b = button(win, label)
    if b is None:
        print('BUTTON NOT FOUND:', label)
        return False
    print('click:', label, '(state=%s)' % b.cget('state'))
    if b.cget('state') == 'disabled':
        return False
    b.invoke()
    pump(root, wait)
    return True


def wait_done(root, win, seconds=240):
    """Waits for the background thread of the window (map build + game start) and its message."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        pump(root, 0.5)
        if not win.busy and time.time() - t0 > 1.0:
            return True
    return False


def ledger(flow):
    s = flow.state()
    return s['stock'], [e['kind'] for e in s['ledger']], {k: (v['mission'], v['state']) for k, v in s['operations'].items()}


def main(step):
    root, win, flow = open_window()
    try:
        if step == 'state':
            print(json.dumps(flow.state(), indent=1, ensure_ascii=False)[:3000])
        elif step == 'shortage':
            print('stock', flow.stock())
            show(win)
            pay = button(win, 'Оплатить и начать')
            print('pay button state:', pay.cget('state') if pay else None)
            ok, msg, op = flow.start_new('traynor03', 'standard', dict(win.order))
            print('forced call ->', ok, msg)
            print('after:', ledger(flow))
        elif step == 'start1':
            show(win)
            click(root, win, 'Начать «Вне закона»')
            print('thread finished:', wait_done(root, win))
            show(win)
            print('state:', ledger(flow))
        elif step == 'accept':
            pump(root, 2.0)
            show(win)
            click(root, win, 'Принять этот результат')
            show(win)
            print('state:', ledger(flow))
            print('second click possible:', button(win, 'Принять этот результат') is not None)
        elif step == 'pay':
            show(win)
            click(root, win, 'Рекомендуемый заказ')
            show(win)
            before = flow.stock()
            click(root, win, 'Оплатить и начать')
            print('thread finished:', wait_done(root, win))
            show(win)
            print('stock before', before, 'after', flow.stock())
            print('state:', ledger(flow))
        elif step in ('continue', 'restart'):
            show(win)
            click(root, win, 'Продолжить сохранение' if step == 'continue' else 'Перезапустить (бесплатно)')
            print('thread finished:', wait_done(root, win))
            show(win)
            print('launch:', flow.state().get('launch'))
            print('state:', ledger(flow))
        else:
            print('unknown step')
            return 2
    finally:
        pump(root, 0.5)
        root.destroy()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'state'))
