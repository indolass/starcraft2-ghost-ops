"""Check of the REAL campaign window (CustomTkinter from tmp/thirdparty/ctk, the launcher's own environment) on COPIES of the Owner's data.

Nothing of the Owner is touched: the campaign file and the Bank are copied into a temporary APPDATA, the backend is a fake that never starts a game, buttons are
pressed with CTkButton.invoke() (the same call a click makes). Prints PASS / FAIL lines and exits 1 on any FAIL.

  python tools/ui_check_campaign.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tmp', 'thirdparty', 'ctk'))
os.environ.setdefault('GHOSTOPS_LINES_DIR', os.path.join(ROOT, 'tests', 'no_shared_lines_here'))

REAL_APPDATA = os.environ.get('APPDATA')
REAL_BANK = os.path.join(os.path.expanduser('~'), 'Documents', 'StarCraft II', 'Banks', 'GhostOpsCampaign.SC2Bank')
REAL_CAMPAIGN = os.path.join(REAL_APPDATA, 'GhostOps', 'campaign.json')

tmp = tempfile.mkdtemp(prefix='ghostops_ui_')
os.environ['APPDATA'] = tmp  # campaign.APP_DIR (plans, bank_archive) lives in the temporary folder
os.makedirs(os.path.join(tmp, 'GhostOps'))
os.makedirs(os.path.join(tmp, 'Banks'))
shutil.copy2(REAL_CAMPAIGN, os.path.join(tmp, 'GhostOps', 'campaign.json'))
shutil.copy2(REAL_BANK, os.path.join(tmp, 'Banks', 'GhostOpsCampaign.SC2Bank'))
os.environ['GHOSTOPS_CAMPAIGN_FILE'] = os.path.join(tmp, 'GhostOps', 'campaign.json')
os.environ['GHOSTOPS_BANK_DIR'] = os.path.join(tmp, 'Banks')

import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402
import customtkinter as ctk  # noqa: E402
import gui_campaign  # noqa: E402
import gui_launcher as gl  # noqa: E402

campaign.APP_DIR = os.path.join(tmp, 'GhostOps')
FAILS = []


def check(name, ok, extra=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (('  | ' + str(extra)) if extra else ''))
    if not ok:
        FAILS.append(name)


class Fake:
    """No game is ever started: prepare / start only record what the flow asked for."""
    def __init__(self):
        self.prepared, self.started = [], []

    def sc2_running(self):
        return False

    def prepare(self, args, mode, progress):
        self.prepared.append((args.mission, args.preset, mode, args.plan))
        return 0

    def manifest(self, args):
        return {'data_hash': 'HASH-%s-%s' % (args.mission, args.preset)}

    def start(self, args):
        self.started.append((args.mission, args.preset))
        return 0


def texts(widget, out=None):
    out = [] if out is None else out
    for c in widget.winfo_children():
        for key in ('text',):
            try:
                t = c.cget(key)
                if t:
                    out.append((c, t))
            except Exception:  # noqa: BLE001 - not every widget has a text
                pass
        texts(c, out)
    return out


def alltext(win):
    return '\n'.join(t for _, t in texts(win.body))


def button(win, label):
    for c, t in texts(win.body):
        if t == label and hasattr(c, 'invoke'):
            return c
    return None


def open_window(root, flow):
    w = gui_campaign.make_window_class(ctk, dict(BG=gl.BG, PANEL=gl.PANEL, CARD=gl.CARD, LINE=gl.LINE, ACCENT=gl.ACCENT, ACCENT_HOVER=gl.ACCENT_HOVER, TEXT=gl.TEXT, MUTED=gl.MUTED,
                                                  AMBER=gl.AMBER, RED=gl.RED, GREEN=gl.GREEN, FONT=gl.FONT))(root, flow=flow)
    w.update()
    return w


def pump(w, seconds=1.2):
    end = time.time() + seconds
    while time.time() < end:
        w.update()
        time.sleep(0.05)


def main():
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    root.geometry('1x1+0+0')
    root.attributes('-alpha', 0.0)
    root.update()
    fake = Fake()
    flow = cf.CampaignFlow(fake)
    st0 = flow.state()
    check('copy of the Owner data: stock 0 / 0, no operation', st0['stock'] == {'minerals': 0, 'gas': 0} and not st0['operations'])

    w = open_window(root, flow)
    text = alltext(w)
    check('the found standalone result is shown and waits for acceptance', 'ожидает принятия' in text, text[:0])
    check('exact numbers 5636 minerals / 275 gas', '5636 минералов, 275 газа' in text)
    check('the source is plain text (profile "Вне закона, версия 2", launcher card, game time)', 'Вне закона, версия 2' in text and 'запущенное с карточки запускателя' in text and '876 с' in text)
    check('technical ids are behind "Подробнее", not shown by default', 'A676049589-499230426' not in text and '2fbc909853f73d1c' not in text and button(w, 'Подробнее') is not None)
    button(w, 'Подробнее').invoke()
    pump(w, 0.3)
    t2 = alltext(w)
    print([ln for ln in t2.splitlines() if 'Технические' in ln or 'A676' in ln][:2])
    check('"Подробнее" shows the result id, the hash, the profile and the file', 'A676049589-499230426' in t2 and '2fbc909853f73d1c' in t2 and 'tactical_next' in t2 and 'GhostOpsCampaign.SC2Bank' in t2)
    button(w, 'Скрыть подробности').invoke()
    # --- the new operation of the first mission uses the CURRENT version
    start = button(w, 'Начать «Вне закона»')
    check('the start button of "Вне закона" exists (nothing is accepted yet)', start is not None)
    # --- the confirm button
    adopt = button(w, 'Зачислить в кампанию (один раз)')
    check('the confirm button exists and is enabled', adopt is not None and str(adopt.cget('state')) == 'normal')
    adopt.invoke()
    pump(w, 0.4)
    check('the campaign stock is updated to 5636 / 275', flow.stock() == {'minerals': 5636, 'gas': 275} and 'Запас кампании: 5636 минералов, 275 газа' in alltext(w), flow.stock())
    check('the second adoption is not offered (no confirm button, "уже зачислен")', button(w, 'Зачислить в кампанию (один раз)') is None and 'уже зачислен' in alltext(w))
    try:
        flow.adopt_standalone(flow.standalone_status('traynor02')['results'][0])
        check('a second adoption through the code is refused', False)
    except Exception:  # noqa: BLE001
        check('a second adoption through the code is refused', True)
    check('the stock did not change after the refused repetition', flow.stock() == {'minerals': 5636, 'gas': 275})
    w.destroy()
    pump(root, 0.2)
    # --- closed and opened again: the state is kept
    flow2 = cf.CampaignFlow(Fake())
    w2 = open_window(root, flow2)
    t3 = alltext(w2)
    check('after closing and reopening: the stock is kept and the result is "уже зачислен"', 'Запас кампании: 5636 минералов, 275 газа' in t3 and 'уже зачислен' in t3 and button(w2, 'Зачислить в кампанию (один раз)') is None)
    check('the first mission shows the accepted operation', 'завершена, результат принят' in t3)
    w2.destroy()
    # --- the archived copy of the same journal is not offered again
    os.makedirs(campaign.archive_dir(), exist_ok=True)
    shutil.copy2(os.path.join(tmp, 'Banks', 'GhostOpsCampaign.SC2Bank'), os.path.join(campaign.archive_dir(), 'GhostOpsCampaign_old.SC2Bank'))
    os.remove(os.path.join(tmp, 'Banks', 'GhostOpsCampaign.SC2Bank'))  # the launcher moved it away: only the archived copy is left
    w3 = open_window(root, cf.CampaignFlow(Fake()))
    t4 = alltext(w3)
    check('an archived copy of an already counted result is not offered again', button(w3, 'Зачислить в кампанию (один раз)') is None and 'уже зачислен' in t4)
    w3.destroy()
    # --- a missing journal gives a concrete reason
    shutil.rmtree(campaign.archive_dir())
    w4 = open_window(root, cf.CampaignFlow(Fake()))
    st = cf.CampaignFlow(Fake()).standalone_status('traynor02')
    check('with the result already counted and no journal the window still says "уже зачислен" (the ledger remembers)', 'Результат' in alltext(w4), st['state'])
    w4.destroy()

    # --- fresh copy of the data for the campaign buttons
    os.remove(os.environ['GHOSTOPS_CAMPAIGN_FILE'])
    fake = Fake()
    flow = cf.CampaignFlow(fake)
    w5 = open_window(root, flow)
    t5 = alltext(w5)
    check('no journal and no operation: "Результат не найден" with the concrete reason', 'Результат не найден' in t5 and 'отсутствует' in t5, [l for l in t5.split('\n') if 'не найден' in l][:1])
    b = button(w5, 'Начать «Вне закона»')
    b.invoke()
    pump(w5, 2.5)
    ops = flow.state()['operations']
    check('the real button starts "Вне закона" on tactical_next', len(fake.started) == 1 and fake.started[0] == ('traynor02', 'tactical_next') and [o['profile'] for o in ops.values()] == ['tactical_next'], (fake.started, [o['profile'] for o in ops.values()]))
    op_id = list(ops)[0]
    w5.destroy()
    # --- an OLD operation (profile tactical) continues with ITS profile, existing set, no new payment
    st = flow.state()
    stock_before = dict(st['stock'])
    old = {'mission': 'traynor02', 'profile': 'tactical', 'cost': {'minerals': 0, 'gas': 0}, 'handed': {}, 'data_hash': 'OLDHASH', 'order': None, 'state': 'started',
           'attempts': {'A1': {'state': 'live', 'hash': 'OLDHASH'}}, 'accepted_result': None, 'created': time.time()}
    del st['operations'][op_id]
    st['operations']['OP0001'] = old
    campaign.commit(flow.path, st)
    fake = Fake()
    flow = cf.CampaignFlow(fake)
    w6 = open_window(root, flow)
    b = button(w6, 'Продолжить сохранение')
    check('the old operation offers "Продолжить сохранение"', b is not None)
    b.invoke()
    pump(w6, 2.5)
    check('continuing uses the OLD profile and the existing set (mode existing), no payment', fake.prepared and fake.prepared[0][1] == 'tactical' and fake.prepared[0][2] == 'existing' and flow.stock() == stock_before
          and fake.started == [('traynor02', 'tactical')], (fake.prepared, fake.started))
    w6.destroy()
    # --- the variants of "Час икс"
    st = flow.state()
    st['operations']['OP0001']['state'] = 'accepted'
    st['stock'] = {'minerals': 5000, 'gas': 0}
    campaign.commit(flow.path, st)
    fake = Fake()
    flow = cf.CampaignFlow(fake)
    w7 = open_window(root, flow)
    t7 = alltext(w7)
    check('the current "Час икс" (defence_next, version 2) is the default and clearly named', 'версия 2 — ТЕКУЩАЯ' in t7 and button(w7, 'Оборона и диверсии, версия 2 (текущая)') is not None)
    check('the earlier variants are separate buttons', button(w7, 'Оборона и диверсии, версия 1') is not None and button(w7, 'Прежний «Час икс»') is not None)
    button(w7, 'Оборона и диверсии, версия 1').invoke()
    pump(w7, 0.3)
    check('version 1 is described as the earlier map', 'версия 1 — прежняя' in alltext(w7))
    button(w7, 'Оборона и диверсии, версия 2 (текущая)').invoke()
    pump(w7, 0.3)
    pay = button(w7, 'Оплатить и начать')
    check('the order of version 2 can be paid and started', pay is not None and str(pay.cget('state')) == 'normal')
    pay.invoke()
    pump(w7, 2.5)
    ops = flow.state()['operations']
    new = [o for k, o in ops.items() if o['mission'] == 'traynor03']
    check('the paid operation of "Час икс" is on defence_next, charged once', len(new) == 1 and new[0]['profile'] == 'defence_next' and flow.stock()['minerals'] == 5000 - 1640 and fake.started == [('traynor03', 'defence_next')],
          (fake.started, flow.stock(), [o['profile'] for o in new]))
    w7.destroy()
    root.destroy()
    # the Owner's real files are untouched
    real_state = json.load(open(REAL_CAMPAIGN, encoding='utf-8'))
    check('the real campaign.json of the Owner is untouched (stock 0 / 0, nothing accepted)', real_state['stock'] == {'minerals': 0, 'gas': 0} and not real_state['accepted_results'] and not real_state['operations'])
    shutil.rmtree(tmp, ignore_errors=True)
    print('FAILED: %d' % len(FAILS) if FAILS else 'ALL PASSED')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
