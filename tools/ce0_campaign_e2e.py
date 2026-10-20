"""CE-1 end-to-end check in the REAL game with the REAL launcher-side flow (development tool; test files only).

  python tools/ce0_campaign_e2e.py step1   # TRaynor02 (probe preset) through CampaignFlow: operation, unique map, small muted test window
  (then: ce0_session.py cmd "win" ; close the game ; python tools/ce0_campaign_e2e.py step2)
  python tools/ce0_campaign_e2e.py step2   # reads the journal, shows the proposal, accepts it once, quotes and starts the TRaynor03 operation with the paid order

The campaign file is tmp/ce0/e2e_campaign.json (never the Owner's %APPDATA% file); the flow starts the game exactly as the launcher does, except for the window (the test window rules of
CLAUDE.md: small window, our own process muted, never touching a game that is not ours).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build  # noqa: E402
import campaign  # noqa: E402
import campaign_flow as cf  # noqa: E402
import monitors  # noqa: E402
import test_launch  # noqa: E402

E2E_FILE = os.path.join(ROOT, 'tmp', 'ce0', 'e2e_campaign.json')
SESSION = os.path.join(ROOT, 'tmp', 'ce0', 'session.json')


class TestWindowBackend(cf.BuildCampaignBackend):
    def start(self, args):
        if test_launch.sc2_pids():
            print('StarCraft II is already running (not ours): refused')
            return 9
        adapter, cfg, name = build.context(args)
        mon, second = monitors.test_monitor(monitors.list_monitors())
        x, y, w, h = monitors.test_window_rect(mon, 1024, 768)
        command, dest = test_launch.test_command(adapter, cfg, name, x, y, w, h)
        before = test_launch.sc2_pids()
        build.start_detached(command)
        pid = test_launch.wait_new_pid(before)
        if pid is None:
            return 8
        subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'mute_process.ps1'), '-ProcessId', str(pid), '-Seconds', '3000'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        win = test_launch.place_window(pid, (x, y, w, h))
        json.dump({'pid': pid, 'mission': args.mission, 'preset': name, 'started': time.time(), 'map': dest, 'second_monitor': second,
                   'window': win and win['rect'], 'command': command, 'operation': adapter.get('_op')}, open(SESSION, 'w'), indent=2)
        print('test game pid %d, window %s, second monitor: %s' % (pid, win and win['rect'], second))
        return 0


def flow():
    os.environ['GHOSTOPS_CAMPAIGN_FILE'] = E2E_FILE
    campaign.APP_DIR = os.path.join(ROOT, 'tmp', 'ce0', 'e2e_appdata')
    return cf.CampaignFlow(TestWindowBackend(), path=E2E_FILE)


def main(step):
    f = flow()
    if step == 'step1':
        ok, msg, op = f.start_new('traynor02', 'ce0_dev')
        print(ok, msg, op)
        return 0 if ok else 1
    if step == 'step2':
        got = f.after_exit()
        print('operation', got['op'], 'fresh', got.get('fresh'), 'proposals', len(got['proposals']), 'held', got['held'])
        for p in got['proposals']:
            print(' proposal', p['result_id'], p['minerals'], p['gas'])
            print('\n'.join(campaign.report_lines(campaign.report(p))))
        if not got['proposals']:
            return 1
        rep = f.accept(got['proposals'][0])
        print('accepted once; stock now', f.stock())
        try:
            f.accept(got['proposals'][0])
        except campaign.Rejected as e:
            print('second acceptance refused:', e)
        info = f.order_info('traynor03', 'standard_dev')
        stock = f.stock()['minerals']
        order = {'marines': max(0, min(info['limits']['marines'], stock // 40)), 'bunkers': 0, 'turrets': 0, 'scvs': 0}  # what the real remainder of this short test pays for
        q = f.quote('traynor03', 'standard_dev', order)
        print('quote', q)
        if not q['ok']:
            return 2
        ok, msg, op = f.start_new('traynor03', 'standard_dev', order)
        print(ok, msg, op, 'stock after payment', f.stock())
        return 0 if ok else 3
    return 9


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
