"""TRaynor03 campaign path through the REAL campaign window (CustomTkinter widgets) with the REAL backend (build + install + start of the game in the small muted test window).
Development tool, test data only (its own campaign file, its own journal Bank, a made-up stock; the Owner's campaign file, Bank and saves are never touched).

  A. a NEW operation: the window recommends version 6 (`defence_r6`) -> recommended order -> pay once -> the unique map set of version 6 is built, installed and started
  B. the same operation is continued from the window: no second payment, the same map
  C. an OLD paid operation of version 2 (`defence_next`) is continued from the window: its own earlier map (not version 6), no payment

The maps of the test operations are removed at the end (their names carry the test operation numbers OP0091+, no Owner operation uses them).

  python tools/test_queue.py enqueue --label tr3gui --mission traynor03 --preset defence_r6 -- python tools/tr3_campaign_gui_e2e.py
"""
import json
import os
import sys
import time

os.environ['GHOSTOPS_CAMPAIGN_BANK'] = 'GhostOpsDevCamp'  # before the campaign module is imported
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tmp', 'thirdparty', 'ctk'))
import build  # noqa: E402
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402
import ce0_campaign_e2e as e2e  # noqa: E402
import ce0_gui_e2e as g  # noqa: E402
import customtkinter as ctk  # noqa: E402
import gui_campaign  # noqa: E402
import gui_launcher  # noqa: E402
import isolation  # noqa: E402
import test_launch  # noqa: E402

OUT = os.environ.get('GHOSTOPS_E2E_RESULT') or os.path.join(ROOT, 'tmp', 'tr3_campaign_gui_e2e_result.json')
RESULT = []
FILE_A = os.path.join(ROOT, 'tmp', 'r3gui', 'campaign_new.json')
FILE_B = os.path.join(ROOT, 'tmp', 'r3gui', 'campaign_old.json')
SEED = 'OP0090'


def say(msg, **kw):
    kw['msg'] = msg
    RESULT.append(kw)
    print(msg, kw if kw else '')
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(RESULT, f, indent=1, ensure_ascii=False)


def check(label, cond, detail=''):
    say(('PASS ' if cond else 'FAIL ') + label, ok=bool(cond), detail=str(detail))
    return bool(cond)


def seed(path, minerals, gas):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    st = campaign.new_campaign(minerals, gas)
    # a made-up accepted operation of another mission: only so that the numbering of the test operations starts high (names never meet an Owner operation)
    st['operations'][SEED] = {'mission': 'traynor02', 'profile': 'tactical_next', 'state': 'accepted'}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=1)


def open_window(path):
    os.environ['GHOSTOPS_CAMPAIGN_FILE'] = path
    campaign.APP_DIR = os.path.join(ROOT, 'tmp', 'r3gui', 'appdata')
    flow = cf.CampaignFlow(e2e.TestWindowBackend(), path=path)
    root = ctk.CTk()
    root.title('Ghost Ops campaign GUI test (host)')
    root.geometry('320x90+40+40')
    pal = dict(BG=gui_launcher.BG, PANEL=gui_launcher.PANEL, CARD=gui_launcher.CARD, LINE=gui_launcher.LINE, ACCENT=gui_launcher.ACCENT, ACCENT_HOVER=gui_launcher.ACCENT_HOVER,
               TEXT=gui_launcher.TEXT, MUTED=gui_launcher.MUTED, AMBER=gui_launcher.AMBER, RED=gui_launcher.RED, GREEN=gui_launcher.GREEN, FONT=gui_launcher.FONT)
    win = gui_campaign.make_window_class(ctk, pal)(root, flow=flow)
    g.pump(root, 1.0)
    return root, win, flow


def session():
    with open(e2e.SESSION, encoding='utf-8') as f:
        return json.load(f)


def close_game():
    st = session()
    if st['pid'] in test_launch.sc2_pids() and isolation.is_owned(st['pid']):
        isolation.close_owned(st['pid'])
        time.sleep(4)
        return True
    return False


def op_of(flow, mission):
    return next(((k, v) for k, v in flow.state()['operations'].items() if v['mission'] == mission and k != SEED), (None, None))


def main():
    removed = []
    try:
        # ---- A: a new operation -------------------------------------------------------------------------------------------------------
        seed(FILE_A, 5000, 2000)
        root, win, flow = open_window(FILE_A)
        check('A1 the window recommends version 6 for a new operation', win.t3 == 'defence_r6' and cf.step_of('traynor03')['preset'] == 'defence_r6', win.t3)
        texts = g.all_text(win)
        check('A2 the card says it is the current version', any('версия 6 — ТЕКУЩАЯ' in t for t in texts))
        check('A3 the earlier versions are labelled as earlier', any('Версия 4 (прежняя)' in t for t in texts) and any('Версия 2 (прежняя)' in t for t in texts))
        g.click(root, win, 'Рекомендуемый заказ')
        order = dict(win.order)
        q = flow.quote('traynor03', 'defence_r6', order)
        check('A4 the recommended order is valid and its cost is shown', q['ok'], q)
        before = flow.stock()
        g.click(root, win, 'Оплатить и начать')
        g.wait_done(root, win, 420)
        op_id, op = op_of(flow, 'traynor03')
        check('A5 one operation, paid once, profile version 6', op is not None and op['profile'] == 'defence_r6', op)
        after = flow.stock()
        check('A6 the stock fell by exactly the quoted cost', before['minerals'] - after['minerals'] == q['cost']['minerals'] and before['gas'] - after['gas'] == q['cost']['gas'], (before, after, q['cost']))
        plan = json.load(open(os.path.join(cf.plans_dir(), op_id + '.json'), encoding='utf-8'))
        check('A7 the plan holds the version-6 profile and the order', plan['preset'] == 'defence_r6' and plan.get('order') == order, plan)
        st = session()
        check('A8 the started map is the unique version-6 map of the operation', st['preset'].startswith('defence_r6') and ('__' + op_id) in os.path.basename(st['map']) and os.path.isfile(st['map']), st['map'])
        removed.append(st['map'])
        check('A10 the test game of A is closed (our own pid only)', close_game())
        root.destroy()

        # ---- B: the same operation continued ---------------------------------------------------------------------------------------------
        root, win, flow = open_window(FILE_A)
        texts = g.all_text(win)
        check('B1 the window shows the operation map as version 6', any('Карта операции: Оборона и диверсии, версия 6' in t for t in texts))
        before = flow.stock()
        g.click(root, win, 'Продолжить сохранение')
        g.wait_done(root, win, 420)
        st2 = session()
        check('B2 no second payment', flow.stock() == before, (before, flow.stock()))
        check('B3 the same map file is started', st2['map'] == st['map'], st2['map'])
        check('B4 the test game of B is closed', close_game())
        root.destroy()

        # ---- C: an old paid operation (version 2) continues with its own map --------------------------------------------------------------
        seed(FILE_B, 5000, 2000)
        os.environ['GHOSTOPS_CAMPAIGN_FILE'] = FILE_B
        campaign.APP_DIR = os.path.join(ROOT, 'tmp', 'r3gui', 'appdata')
        flow_old = cf.CampaignFlow(e2e.TestWindowBackend(), path=FILE_B)
        info = flow_old.order_info('traynor03', 'defence_next')
        ok, msg, oid = flow_old.start_new('traynor03', 'defence_next', dict(info['recommended']))  # created like an old paid operation (the profile of the earlier version)
        check('C1 the old operation is paid and started on its own profile', ok, msg)
        st3 = session()
        removed.append(st3['map'])
        check('C2 its map is the version-2 map', st3['preset'].startswith('defence_next') and ('__' + oid) in os.path.basename(st3['map']), st3['map'])
        check('C3 the old-operation game is closed', close_game())
        root, win, flow = open_window(FILE_B)
        check('C4 the window of the old operation shows version 2 (earlier) as its map', any('Карта операции: Оборона и диверсии, версия 2 (прежняя)' in t for t in g.all_text(win)))
        before = flow.stock()
        g.click(root, win, 'Продолжить сохранение')
        g.wait_done(root, win, 420)
        st4 = session()
        check('C5 continuing starts the OLD map, not version 6', st4['map'] == st3['map'] and 'defence_r6' not in os.path.basename(st4['map']), st4['map'])
        check('C6 no payment on continuing', flow.stock() == before)
        check('C7 the operation profile stayed defence_next', flow.state()['operations'][oid]['profile'] == 'defence_next')
        check('C8 the test game of C is closed', close_game())
        root.destroy()
    finally:
        # the test operations' maps only (their own unique names); nothing else is touched
        time.sleep(2)
        for p in removed:
            try:
                if os.path.isfile(p) and '__OP009' in os.path.basename(p):
                    os.remove(p)
                    say('removed test map', path=p)
            except OSError as e:
                say('could not remove test map', path=p, error=str(e))
    bad = [r for r in RESULT if r.get('ok') is False]
    say('SUMMARY', failed=len(bad), total=len([r for r in RESULT if 'ok' in r]))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
