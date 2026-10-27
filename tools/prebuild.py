"""Prepares the CURRENT maps (not the earlier versions) of the three playable missions in advance: build, check and install; a map that is already up to date is skipped (nothing is
rebuilt, nothing is copied). The three stages are timed separately. A protected map of the Owner is never touched; a running game stops the run (this tool never closes it).

  python tools/prebuild.py [--mission M ...] [--status-only] [--force-times]
"""
import argparse
import contextlib
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build  # noqa: E402
import launcher_core as core  # noqa: E402

MISSIONS = ('traynor03', 'thanson01', 'thanson02')


def current_profiles(mission):
    """The profiles of the mission that are not marked as an earlier version: the default (recommended) one and the free tests of the current revision."""
    names = []
    for p in core.profiles_of(mission):
        if 'Прежняя' in (p.get('badge') or ''):
            continue
        if p['name'] in ('standard', 'defence', 'defence_next', 'sniper', 'sniper_next', 'epidemic_free', 'epidemic_free_r2', 'sniper_next_free_r2'):
            continue
        names.append(p['name'])
    d = core.default_profile(mission)
    if d and d not in names:
        names.insert(0, d)
    return names


def args_for(mission, preset):
    return argparse.Namespace(mission=mission, preset=preset, source=None, multiplier=None, diag=False, print_only=False, start=False, no_voice=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--mission', action='append')
    ap.add_argument('--status-only', action='store_true')
    a = ap.parse_args(argv)
    rows = []
    if build.sc2_running() and not a.status_only:
        print('StarCraft II is running: close it yourself first (this tool never closes it).')
        return 7
    for m in (a.mission or MISSIONS):
        for preset in current_profiles(m):
            t0 = time.time()
            st = build.build_status(args_for(m, preset))
            t_status = time.time() - t0
            if a.status_only or st == 'ready':
                rows.append((m, preset, st, t_status, 0.0, 0.0, 0.0))
                continue
            stages = {}
            last = [None, time.time()]

            def note(stage):
                now = time.time()
                if last[0]:
                    stages[last[0]] = stages.get(last[0], 0.0) + (now - last[1])
                last[0], last[1] = stage, now
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = build.prepare(args_for(m, preset), note)
            note(None)
            rows.append((m, preset, 'built' if rc == 0 else 'FAILED rc=%s' % rc, t_status, stages.get('build', 0.0), stages.get('verify', 0.0), stages.get('install', 0.0)))
            if rc != 0:
                print(buf.getvalue()[-800:])
    print('%-10s %-28s %-14s %8s %8s %8s %8s' % ('mission', 'profile', 'result', 'status s', 'build s', 'check s', 'install s'))
    for r in rows:
        print('%-10s %-28s %-14s %8.2f %8.2f %8.2f %8.2f' % r)
    return 0 if all(not r[2].startswith('FAILED') for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
