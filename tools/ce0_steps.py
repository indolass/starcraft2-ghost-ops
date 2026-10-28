"""Prepared in-game check as data: runs a list of bounded steps against ONE test game of a hidden dev preset (developer tool; started by tools/test_queue.py).

  python tools/ce0_steps.py scenarios/salvo_friendly_fire.json [--result FILE]

Scenario file: {"name": ..., "mission": "traynor03", "preset": "defence_next_dev", "steps": [ {"op": ...}, ... ]}
Steps (every one is bounded; nothing loops forever):
  start                      start the test game through the test-launch guard (exit code 9 = a game is running: the queue puts the job back to waiting)
  wait_snap [timeout]        wait for the mission-start line of the probe journal, then `settle` seconds (default 12)
  key KEYS...                posted keys into OUR window ("keys": ["ESC"])
  cmd TEXT [wait]            a probe command typed into the game chat
  sleep S
  expect_def REGEX [count]   like expect, over the log bank of the defence module (exact number of matching lines with count)
  drag X1 Y1 X2 Y2           posted left-button drag (the selection box of the player)
  click X Y                  posted left click into OUR window (client coordinates)
  move X Y                   posted mouse-move into OUR window (client coordinates)
  until GREP [cmd] [every] [timeout]   repeat `cmd` until the regexp GREP appears in the journal lines after the last mark (fails the scenario on timeout)
  retry STEPS CHECK GREP     repeat a real-input action until the probe line CHECK matches GREP (up to `tries`)
  mark                       remember the end of the journal (later `expect` / `until` look only after it)
  expect REGEX [absent]      the regexp must (or, with absent, must not) match a journal line after the mark; the matching lines go to the result
  save NAME / load NAME      the real save / load menu of the game (layout of the 1024x768 test window)
  shot FILE                  screenshot of OUR window
  stop                       close OUR game (always done at the end, even after a failure)
The result (JSON: every step, the matching journal lines, ok flag) is written next to the job log; exit code 0 only when every expect held.
"""
import argparse
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce0_session  # noqa: E402
import sc2_ui  # noqa: E402
import test_launch  # noqa: E402

LAYOUT = {839: {'save': (460, 333), 'load': (586, 333), 'item': (360, 333), 'ok': (922, 713)}, 791: {'save': (465, 315), 'load': (586, 315), 'item': (330, 316), 'ok': (905, 672)}}
SAVES = os.path.join(test_launch.DOCS, 'Saves')


def _client(p):
    return (p[0] - 13, p[1] - 59)


class Scenario:
    def __init__(self, spec, result_path):
        self.spec = spec
        self.result_path = result_path
        self.mark_n = 0
        self.log = []
        self.ok = True
        self.started = False

    # -- journal helpers
    def rows(self):
        return [(n, t) for n, t in ce0_session.journal('j', 0)]

    def after_mark(self):
        return [(n, t) for n, t in self.rows() if n > self.mark_n]

    def chat(self, text, wait=1.5):
        st = ce0_session.load_state()
        sc2_ui.key(st['pid'], ['ENTER'], 0.4)
        sc2_ui.type_text(st['pid'], text)
        time.sleep(0.3)
        sc2_ui.key(st['pid'], ['ENTER'], 0.4)
        time.sleep(wait)

    def record(self, step, **kw):
        kw['step'] = step
        self.log.append(kw)
        with open(self.result_path, 'w', encoding='utf-8') as f:
            json.dump({'name': self.spec.get('name'), 'ok': self.ok, 'steps': self.log}, f, indent=2, ensure_ascii=False)

    # -- steps
    def op_start(self, s):
        ns = argparse.Namespace(mission=self.spec['mission'], preset=self.spec['preset'], width=1024, height=768, keep_bank=False, save=None, no_prepare=True, plan=None,
                                mute_seconds=int(s.get('mute_seconds', 3000)))
        rc = ce0_session.cmd_start(ns)
        self.started = rc == 0
        self.record('start', rc=rc)
        if rc != 0:
            raise SystemExit(9 if rc == 9 else 8)

    def op_wait_snap(self, s):
        end = time.time() + s.get('timeout', 150)
        while time.time() < end:
            if any('SNAP start' in t for _, t in self.rows()):
                time.sleep(s.get('settle', 12))
                self.record('wait_snap', ok=True)
                return
            time.sleep(3)
        self.ok = False
        self.record('wait_snap', ok=False)
        raise SystemExit(1)

    def op_key(self, s):
        sc2_ui.key(ce0_session.load_state()['pid'], s['keys'], 0.5)
        self.record('key', keys=s['keys'])

    def op_cmd(self, s):
        self.chat(s['text'], s.get('wait', 1.5))
        self.record('cmd', text=s['text'])

    def op_char(self, s):
        sc2_ui.char(ce0_session.load_state()['pid'], s['text'])
        self.record('char', text=s['text'])

    def op_scankey(self, s):
        sc2_ui.scan_key(ce0_session.load_state()['pid'], s['text'])
        self.record('scankey', text=s['text'])

    def op_move(self, s):
        sc2_ui.move(ce0_session.load_state()['pid'], s['x'], s['y'])
        self.record('move', x=s['x'], y=s['y'])

    def op_click(self, s):
        sc2_ui.click(ce0_session.load_state()['pid'], s['x'], s['y'])
        self.record('click', x=s['x'], y=s['y'])

    def op_drag(self, s):
        sc2_ui.drag(ce0_session.load_state()['pid'], s['x1'], s['y1'], s['x2'], s['y2'])
        self.record('drag', x1=s['x1'], y1=s['y1'], x2=s['x2'], y2=s['y2'])

    def op_rclick(self, s):
        sc2_ui.rclick(ce0_session.load_state()['pid'], s['x'], s['y'])
        self.record('rclick', x=s['x'], y=s['y'])

    def op_expect_def(self, s):
        """The same as expect, but over the log Bank of the defence module (GhostOpsDevDef: scenes, landings, waves): `count` = the exact number of matching lines (default: at least one)."""
        rx = re.compile(s['regex'])
        rows = []
        for f in ce0_session.bank_files(s.get('bank', 'GhostOpsDevDef')):
            for k, v in ce0_session.read_bank(f).get('log', {}).items():
                rows.append(v)
        hits = [t for t in rows if rx.search(t)]
        good = (len(hits) == s['count']) if 'count' in s else bool(hits)
        if not good:
            self.ok = False
        self.record('expect_def', regex=s['regex'], count=s.get('count'), found=len(hits), ok=good, lines=hits[-80:], note=s.get('note', ''))

    def op_sleep(self, s):
        time.sleep(s['s'])
        self.record('sleep', s=s['s'])

    def op_mark(self, s):
        rows = self.rows()
        self.mark_n = max([n for n, _ in rows] or [0])
        self.record('mark', n=self.mark_n)

    def op_retry(self, s):
        """A real-input action that can be spoilt by something outside it (the original scenario pans the camera at the start of a night wave: a click then lands on another place): the sub-steps are done, the probe `check` is asked
        and, when its line does not match `grep`, the whole action is repeated (up to `tries`). Every attempt is recorded: the result says how many were needed."""
        rx = re.compile(s['grep'])
        for attempt in range(1, int(s.get('tries', 3)) + 1):
            for st in s['steps']:
                getattr(self, 'op_' + st['op'])(st)
            time.sleep(s.get('wait', 6))
            self.op_mark({})
            end = time.time() + s.get('timeout', 24)
            while time.time() < end:
                self.chat(s['check'], 1.0)
                hits = [t for _, t in self.after_mark() if rx.search(t)]
                if hits:
                    self.record('retry', check=s['check'], grep=s['grep'], ok=True, attempts=attempt, line=hits[-1])
                    return
                time.sleep(s.get('every', 4))
            self.record('retry_attempt_failed', check=s['check'], grep=s['grep'], attempt=attempt)
        self.ok = False
        self.record('retry', check=s['check'], grep=s['grep'], ok=False, attempts=int(s.get('tries', 3)))

    def op_until(self, s):
        end = time.time() + s.get('timeout', 120)
        rx = re.compile(s['grep'])
        while time.time() < end:
            if s.get('cmd'):
                self.chat(s['cmd'], 1.0)
            hits = [t for _, t in self.after_mark() if rx.search(t)]
            if hits:
                self.record('until', grep=s['grep'], ok=True, line=hits[-1])
                return
            time.sleep(s.get('every', 4))
        self.ok = False
        self.record('until', grep=s['grep'], ok=False)
        raise SystemExit(1)

    def op_expect(self, s):
        rx = re.compile(s['regex'])
        hits = [t for _, t in self.after_mark() if rx.search(t)]
        good = (not hits) if s.get('absent') else bool(hits)
        if not good:
            self.ok = False
        self.record('expect', regex=s['regex'], absent=bool(s.get('absent')), ok=good, lines=hits[-400:], note=s.get('note', ''))

    def _menu(self, mode, name):
        pid = ce0_session.load_state()['pid']
        sc2_ui.key(pid, ['F10'], 1.5)
        tmp = os.path.join(os.path.dirname(self.result_path), 'menu.png')
        sc2_ui.shot(pid, tmp)
        from PIL import Image
        h = Image.open(tmp).size[1]
        lay = LAYOUT.get(h) or LAYOUT[839]
        if mode == 'load':
            sc2_ui.click(pid, *_client(lay['load']))
            time.sleep(3)
            sc2_ui.click(pid, *_client(lay['item']))
            time.sleep(0.5)
            sc2_ui.click(pid, *_client(lay['ok']))
            time.sleep(4)
            sc2_ui.key(pid, ['ESC'], 0.5)
            time.sleep(2)
        else:
            sc2_ui.click(pid, *_client(lay['save']))
            time.sleep(2.5)
            sc2_ui.key(pid, ['BACK'] * 20, 0.05)
            sc2_ui.type_text(pid, name)
            time.sleep(0.5)
            sc2_ui.key(pid, ['ENTER'], 1.5)
            time.sleep(3)
            sc2_ui.key(pid, ['ESC'], 0.5)

    def op_save(self, s):
        self._menu('save', s['name'])
        self.record('save', name=s['name'])

    def op_load(self, s):
        self._menu('load', s['name'])
        self.record('load', name=s['name'])

    def op_shot(self, s):
        path = s['file'] if os.path.isabs(s['file']) else os.path.join(os.path.dirname(self.result_path), s['file'])  # next to the result, in the job directory
        ok = sc2_ui.shot(ce0_session.load_state()['pid'], path)
        self.record('shot', file=path, ok=bool(ok))

    def op_burst(self, s):
        """n shots of OUR window in a row; a frame that came out entirely black (the presentation of the game had no new picture: a capture limit, not a picture of the map) is counted and dropped."""
        base = s['file']
        pid = ce0_session.load_state()['pid']
        kept = black = 0
        for i in range(int(s.get('n', 12))):
            path = os.path.join(os.path.dirname(self.result_path), '%s%02d.png' % (base, i))
            if not sc2_ui.shot(pid, path):
                continue
            if os.path.getsize(path) < 20000:
                black += 1
                os.remove(path)
            else:
                kept += 1
            time.sleep(float(s.get('gap', 0)))
        self.record('burst', file=base, kept=kept, black=black)

    def op_origin(self, s):
        """Where the client area starts inside the window picture (the posted mouse messages use client coordinates, the screenshots are of the whole window)."""
        import ctypes
        from ctypes import wintypes as wt
        hwnd, l, t, r, b = sc2_ui.window(ce0_session.load_state()['pid'])
        pt = wt.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        rc = wt.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rc))
        self.record('origin', dx=pt.x - l, dy=pt.y - t, client=(rc.right, rc.bottom), window=(r - l, b - t))

    def op_stop(self, s):
        ce0_session.cmd_stop(argparse.Namespace(keep_map=True, hard=False))
        self.record('stop')

    def cleanup(self):
        try:
            if self.started and os.path.exists(ce0_session.STATE):
                ce0_session.cmd_stop(argparse.Namespace(keep_map=True, hard=False))
        except Exception:  # noqa: BLE001
            pass
        for f in glob.glob(os.path.join(SAVES, '**', 'CE0_*.SC2Save'), recursive=True):  # the check's own saves (never the Owner's)
            try:
                os.remove(f)
            except OSError:
                pass

    def run(self):
        try:
            for s in self.spec['steps']:
                getattr(self, 'op_' + s['op'])(s)
        finally:
            self.cleanup()
        return 0 if self.ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('scenario')
    p.add_argument('--result')
    a = p.parse_args(argv)
    with open(a.scenario, encoding='utf-8') as f:
        spec = json.load(f)
    result = a.result or os.path.join(os.path.dirname(os.environ.get('GHOSTOPS_SESSION_STATE') or ce0_session.STATE), 'result.json')
    os.makedirs(os.path.dirname(result), exist_ok=True)
    return Scenario(spec, result).run()


if __name__ == '__main__':
    sys.exit(main())
