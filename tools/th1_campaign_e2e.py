"""THanson01 campaign path in the REAL game with the REAL launcher-side flow and the REAL campaign window widgets (development tool; test data only).

  payment -> start of the operation (plan, unique map, small muted test window) -> the standard victory chain -> the proposal in the window -> accepted once
  (no second acceptance by a second click, by a re-read of the journal or by a restarted window)

The game is a hidden development preset of the same mission (`sniper_next_r2_campaign_dev`: ordered kits from the plan, the campaign journal and the CE-0 probe). The probe only
sets the quota of saved colonists for the ORIGINAL victory check (`nwin`): the original victory sequence, the journal rows and the proposal are the real ones. This is a
technical check of the economy path, NOT a playthrough.

Test data only: its own campaign file (GHOSTOPS_CAMPAIGN_FILE, set by the queue runner), its own journal Bank GhostOpsDevCamp (config campaign.bank_name; the Owner's Bank
GhostOpsCampaign is never read or written), the stock is a made-up test budget.

  python tools/th1_campaign_e2e.py            # run by the queue:  test_queue.py enqueue ... -- python tools/th1_campaign_e2e.py
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
import argparse  # noqa: E402

import build  # noqa: E402
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402
import ce0_session  # noqa: E402
import ce0_steps  # noqa: E402
import test_launch  # noqa: E402

PLAYABLE = 'sniper_next_r3'
DEV = 'sniper_next_r3_campaign_dev'
OUT = os.environ.get('GHOSTOPS_E2E_RESULT') or os.path.join(ROOT, 'tmp', 'th1_campaign_e2e_result.json')
RESULT = []


def say(msg, **kw):
    kw['msg'] = msg
    RESULT.append(kw)
    print(msg, kw if kw else '')
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(RESULT, f, indent=1, ensure_ascii=False)


def check(label, cond, detail=''):
    say(('PASS ' if cond else 'FAIL ') + label, ok=bool(cond), detail=str(detail))
    return bool(cond)


class Backend(cf.BuildCampaignBackend):
    """The real build, the game in the small muted test window (the test guard of CLAUDE.md), the session state of the queue job."""

    def start(self, args):
        ns = argparse.Namespace(mission=args.mission, preset=args.preset, width=1024, height=768, keep_bank=True, save=None, no_prepare=True, plan=args.plan, mute_seconds=3000)
        return ce0_session.cmd_start(ns)


class DevFlow(cf.CampaignFlow):
    """The window / flow ask for the playable preset; the map is the hidden dev preset of the same mission (probe commands exist there)."""

    def start_new(self, mission, preset, order=None, progress=None):
        return super().start_new(mission, DEV if (mission, preset) == ('thanson01', PLAYABLE) else preset, order, progress)


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def texts(w):
    out = []
    for c in walk(w):
        try:
            t = c.cget('text')
        except Exception:  # noqa: BLE001
            continue
        if t:
            out.append((c, t))
    return out


def open_window(flow):
    import customtkinter as ctk
    import gui_campaign
    import gui_launcher as gl
    ctk.set_appearance_mode('dark')
    root = ctk.CTk()
    root.geometry('1x1+0+0')
    root.attributes('-alpha', 0.0)
    root.update()
    w = gui_campaign.make_window_class(ctk, dict(BG=gl.BG, PANEL=gl.PANEL, CARD=gl.CARD, LINE=gl.LINE, ACCENT=gl.ACCENT, ACCENT_HOVER=gl.ACCENT_HOVER, TEXT=gl.TEXT, MUTED=gl.MUTED,
                                                  AMBER=gl.AMBER, RED=gl.RED, GREEN=gl.GREEN, FONT=gl.FONT))(root, flow=flow)
    w.withdraw()
    for _ in range(10):
        w.update()
        time.sleep(0.05)
    return root, w


def main():
    path = os.environ.get('GHOSTOPS_CAMPAIGN_FILE')
    if not path or os.path.abspath(path).lower().startswith(os.path.join(os.environ.get('APPDATA', ''), 'GhostOps').lower()):
        say('FAIL the campaign file must be a test file (GHOSTOPS_CAMPAIGN_FILE), never the Owner file')
        return 2
    os.environ['GHOSTOPS_BANK_DIR'] = os.path.join(os.path.expanduser('~'), 'Documents', 'StarCraft II', 'Banks')  # where the GAME writes; only the development Bank file GhostOpsDevCamp is used
    campaign.APP_DIR = os.path.join(os.path.dirname(path), 'appdata')
    os.makedirs(campaign.APP_DIR, exist_ok=True)
    flow = DevFlow(Backend(), path=path)
    s = flow.state()
    s['stock'] = {'minerals': 3000, 'gas': 700}  # a made-up test budget; it is the test file's own
    campaign.commit(path, s)
    order = {'turret_kits': 4, 'scvs': 2}
    q = flow.quote('thanson01', PLAYABLE, order)
    check('the order is quoted: 4 kits x 75 + 2 SCVs x 50 + preparation 1000 / 500', q['ok'] and q['cost'] == {'minerals': 4 * 75 + 2 * 50 + 1000, 'gas': 500}, q)
    ok, msg, op = flow.start_new('thanson01', PLAYABLE, order)
    check('paid once and started', ok and flow.stock() == {'minerals': 3000 - 1400, 'gas': 200}, (msg, flow.stock()))
    if not ok:
        return 3
    sc = ce0_steps.Scenario({'name': 'th1_campaign_e2e', 'mission': 'thanson01', 'preset': DEV}, os.path.join(os.path.dirname(path), 'scenario.json'))
    sc.op_wait_snap({'settle': 6})
    sc.op_key({'keys': ['ESC']})
    sc.op_mark({})
    sc.op_until({'cmd': 'nstat', 'grep': 'NSTAT ghosts 2 firebats 2', 'every': 5, 'timeout': 150})
    sc.chat('nstat', 1.5)
    kits = [t for _, t in sc.rows() if 'NSTAT kits' in t]
    check('the map got the PAID order (4 kits), not the default 15', any('ordered 4 ' in t for t in kits), kits[-1:])
    sc.chat('nscv', 1.5)
    scv_rows = [t for _, t in sc.rows() if 'NSCV' in t]
    check('the map got the PAID extra SCVs (2), not the default 8', any('extra ordered 2 ' in t for t in scv_rows), scv_rows[-1:])
    sc.chat('nwin', 1.5)
    deadline = time.time() + 180
    got = None
    while time.time() < deadline:
        got = flow.after_exit()
        if got['proposals']:
            break
        time.sleep(4)
    check('the standard victory chain wrote a RESULT proposal', bool(got and got['proposals']), got and (got['op'], got.get('fresh')))
    ce0_session.cmd_stop(argparse.Namespace(keep_map=True, hard=True))
    time.sleep(3)
    if not got or not got['proposals']:
        return 4
    p = got['proposals'][0]
    say('proposal', result_id=p['result_id'], minerals=p['minerals'], gas=p['gas'], mission=p['mission'], outcome=p['outcome'])
    check('the proposal belongs to this operation and mission', p['op'] == op and p['mission'] == 'thanson01', p['op'])
    before = flow.stock()
    # the REAL window: the card shows the result; one click accepts it
    root, w = open_window(flow)
    w.pending = flow.after_exit()['proposals']
    w.refresh()
    w.update()
    shown = ' '.join(t for _, t in texts(w.body))
    check('the window shows the result and the accept button', 'Принять этот результат' in shown and 'Победа' in shown, shown[:200])
    btn = next((c for c, t in texts(w.body) if t == 'Принять этот результат' and hasattr(c, 'invoke')), None)
    btn.invoke()
    w.update()
    after = flow.stock()
    check('accepted once: the stock grew by exactly the proposal', after['minerals'] == before['minerals'] + p['minerals'] and after['gas'] == before['gas'] + p['gas'], (before, after))
    again = [c for c, t in texts(w.body) if t == 'Принять этот результат']
    check('no accept button after the first acceptance', not again)
    try:
        flow.accept(p)
        check('a second acceptance is refused', False)
    except campaign.Rejected as e:
        check('a second acceptance is refused', True, e)
    check('the stock did not change by the second try', flow.stock() == after, flow.stock())
    w.destroy()
    root.destroy()
    # a restarted window / launcher: the same journal is read again and nothing is offered, nothing is credited
    flow2 = DevFlow(Backend(), path=path)
    got2 = flow2.after_exit()
    check('a re-read of the journal offers nothing', not got2['proposals'], got2['proposals'])
    root2, w2 = open_window(flow2)
    shown2 = ' '.join(t for _, t in texts(w2.body))
    check('a restarted window shows no accept button', 'Принять этот результат' not in shown2)
    w2.destroy()
    root2.destroy()
    check('the stock is still the same after the restart', flow2.stock() == after, flow2.stock())
    check('the paid operation is accepted, nothing is charged again', flow2.state()['operations'][op]['state'] == 'accepted' and flow2.stock()['minerals'] >= after['minerals'])
    bad = [r for r in RESULT if r.get('ok') is False]
    say('ALL PASSED' if not bad else 'FAILED: %d' % len(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
