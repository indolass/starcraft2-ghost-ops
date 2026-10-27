"""Check of the launcher pipeline with the REAL backend (run it through the test queue: it starts the game through the test-launch guard, never the Owner's launch):
the first start of a map, then - after our own test game is closed - the repeat start of the same ready map. Prints the time of every stage and whether the repeat start rebuilt or copied
anything (it must not). The map is the current free test of a mission (not a protected map of the Owner).

  python tools/launcher_repeat_check.py MISSION PRESET
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_launch  # noqa: E402,F401  (sets GHOSTOPS_TEST: every game start goes through the test-launch guard)
import build  # noqa: E402
import isolation  # noqa: E402
import launcher_core as core  # noqa: E402
import procs  # noqa: E402


def map_stamp(mission, preset):
    adapter, cfg, name = build.context(core.BuildBackend().args(mission, preset))
    kept = os.path.join(build.SC2_DIR, 'Maps', 'GhostOps', build.output_name(adapter, name))
    if not os.path.isfile(kept):
        return None
    st = os.stat(kept)
    return (kept, st.st_size, st.st_mtime_ns, hashlib.sha256(open(kept, 'rb').read()).hexdigest()[:12])


def run_once(launcher, mission, preset, label):
    stages = []
    t0 = time.time()
    last = [None, t0]

    def on_stage(s):
        now = time.time()
        stages.append((last[0], now - last[1]))
        last[0], last[1] = s, now
    res = launcher.run(mission, preset, on_stage)
    now = time.time()
    stages.append((last[0], now - last[1]))
    print('%s: ok=%s message=%s total %.1f s; stages %s' % (label, res.ok, res.message, now - t0, ['%s %.1f s' % (k or 'begin', v) for k, v in stages]))
    return res


def main(mission, preset):
    settings = core.Settings()
    launcher = core.Launcher(settings=settings)
    before = map_stamp(mission, preset)
    print('map before the first start:', before)
    print('build_status before: %s' % build.build_status(core.BuildBackend().args(mission, preset)))
    r1 = run_once(launcher, mission, preset, 'first start')
    after1 = map_stamp(mission, preset)
    print('map after the first start:', after1)
    time.sleep(25)
    for pid in procs.pids_of('SC2_x64.exe'):
        print('closing our own test game', pid, 'closed' if isolation.close_owned(pid) else 'NOT closed (not verifiably ours)')
    time.sleep(12)
    if procs.pids_of('SC2_x64.exe'):
        print('a game is still running: the repeat start is skipped')
        return 1
    print('build_status before the repeat: %s' % build.build_status(core.BuildBackend().args(mission, preset)))
    r2 = run_once(launcher, mission, preset, 'repeat start')
    after2 = map_stamp(mission, preset)
    print('map after the repeat start:', after2)
    print('RESULT repeat start did not rebuild or copy the map: %s' % (after1 == after2))
    time.sleep(20)
    for pid in procs.pids_of('SC2_x64.exe'):
        print('closing our own test game', pid, 'closed' if isolation.close_owned(pid) else 'NOT closed (not verifiably ours)')
    return 0 if (r1.ok and r2.ok and after1 == after2) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
