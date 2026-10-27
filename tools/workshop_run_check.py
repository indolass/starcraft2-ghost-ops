"""Check of the Mission Workshop with the REAL build and the test-launch guard (run it through the test queue): create a variant of a mission, change one setting, build it as a free test
(a new map file), start it, close our own test game, start it again (no rebuild, no copy), then change the BASE profile behind its back and show that the built variant does not change.
The variant folder is a temporary one; the variant's map is removed at the end (it was ours). Nothing of the Owner's data is touched.

  python tools/workshop_run_check.py MISSION
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_launch  # noqa: E402,F401  (sets GHOSTOPS_TEST: every game start goes through the test-launch guard)
import build  # noqa: E402
import isolation  # noqa: E402
import procs  # noqa: E402


def close_own():
    for pid in procs.pids_of('SC2_x64.exe'):
        print('closing our own test game', pid, 'closed' if isolation.close_owned(pid) else 'NOT closed (not verifiably ours)')


def main(mission):
    tmp = tempfile.mkdtemp(prefix='wk_run_')
    os.environ['GHOSTOPS_WORKSHOP_DIR'] = tmp
    import workshop
    import gui_workshop
    ok = []

    def check(name, cond, extra=''):
        ok.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + name + (' | ' + str(extra) if extra else ''))
    v = workshop.new_variant(mission, 'Проверка сборки')
    field = {'thanson01': ('snipe_cd', 2.0), 'traynor03': ('grenade_charges', 4), 'thanson02': ('hell_tank', 130)}[mission]
    workshop.set_field(v, field[0], field[1])
    check('draft before the first build', workshop.status(v) == 'draft')
    t0 = time.time()
    rc, msg = workshop.prepare(v, lambda s: None)
    t_build = time.time() - t0
    check('first build', rc == 0, '%s; %.1f s' % (msg, t_build))
    check('ready after the build', workshop.status(v) == 'ready')
    adapter, cfg, preset = build.context(workshop.build_args(v, v['built']['plan']))
    kept = v['built']['map_file']
    check('own map file with the variant id', ('WK' + v['id']) in os.path.basename(kept) and os.path.isfile(kept), os.path.basename(kept))
    check('free test: the plan carries no campaign part', not build.context(workshop.build_args(v, v['built']['plan']))[1].get('campaign'))
    stamp = (os.path.getsize(kept), os.stat(kept).st_mtime_ns)
    backend = gui_workshop.WorkshopBackend()
    t0 = time.time()
    rc = backend.start(v)
    check('first start', rc == 0, 'code %s; %.1f s' % (rc, time.time() - t0))
    time.sleep(25)
    close_own()
    time.sleep(12)
    t0 = time.time()
    rc, msg = workshop.prepare(v, lambda s: None)
    t_repeat = time.time() - t0
    check('repeat prepare does not rebuild', rc == 0 and (os.path.getsize(kept), os.stat(kept).st_mtime_ns) == stamp and v['revision'] == 1, '%.2f s' % t_repeat)
    t0 = time.time()
    rc = backend.start(v)
    check('repeat start', rc == 0, 'code %s; %.1f s' % (rc, time.time() - t0))
    time.sleep(20)
    close_own()
    time.sleep(10)
    # the base profile changes behind the variant: the built variant keeps its snapshot
    real = workshop.resolved_base

    def changed(m, b):
        c = real(m, b)
        c['_changed_marker'] = 1
        return c
    workshop.resolved_base = changed
    try:
        check('base change is noticed', workshop.base_changed(v))
        check('base change does not change the built variant', workshop.status(v) == 'ready' and json.dumps(workshop.effective_cfg(v), sort_keys=True) == json.dumps(v['snapshot'], sort_keys=True))
    finally:
        workshop.resolved_base = real
    # a changed setting is a NEW revision with its own map; the old map stays
    workshop.set_field(v, field[0], field[1] + (1 if isinstance(field[1], int) else 0.5))
    check('changed setting needs a build', workshop.status(v) == 'needs_build')
    old = kept
    rc, msg = workshop.prepare(v, lambda s: None)
    check('new revision built', rc == 0 and v['revision'] == 2 and v['built']['map_file'] != old and os.path.isfile(old) and os.path.isfile(v['built']['map_file']), msg)
    for dest in {old, v['built']['map_file']}:
        key = os.path.basename(dest)
        print('removing our own test map', key)
        try:
            os.remove(dest)
        except OSError as e:
            print('not removed:', e)
    for folder in (build_dir(), os.path.join(os.path.dirname(HERE), 'dist')):
        for name in (os.listdir(folder) if os.path.isdir(folder) else []):
            if ('WK' + v['id']) in name:
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
    shutil.rmtree(tmp, ignore_errors=True)
    print('RESULT %d/%d' % (sum(ok), len(ok)))
    return 0 if all(ok) else 1


def build_dir():
    return os.path.join(os.path.dirname(HERE), 'build')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
