"""Queue of prepared in-game tests: waits for a free StarCraft II, then runs them one by one (developer tool; the Owner's game is never touched).

A job is a concrete, bounded request: one build (mission + hidden preset), one prepared command (normally `python tools/ce0_steps.py <scenario.json>`), a
time limit. The runner never invents jobs, never retries endlessly and keeps going after the Claude conversation is over (it is started detached).

  python tools/test_queue.py enqueue --label L --mission traynor03 --preset defence_next_dev --timeout 900 -- python tools/ce0_steps.py scen.json
  python tools/test_queue.py status [--json]        # jobs, phases, results, log paths
  python tools/test_queue.py cancel [JOB|--all]     # cancels waiting / running jobs; a running test is stopped and ONLY its own game is closed
  python tools/test_queue.py stop                   # no next job is started (a running one finishes); `go` removes the stop flag
  python tools/test_queue.py resume JOB             # an interrupted job (the runner died) is only ever resumed by an explicit command
  python tools/test_queue.py start                  # start the runner detached (enqueue does it too); `run` = the runner in the foreground

Job states: waiting (waiting for a free game / its turn), preparing (build + install of the dev map), running, done, cancelled, error, interrupted
(the runner died while the job was preparing / running: shown, never started again automatically).

Rules of the runner: while ANY StarCraft II process exists it only waits (checks about every 5 s, nothing is closed or changed); after the game disappeared it
waits 10 s, checks again and checks once more right before the launch. A game that appears anyway (conflict with a manual start) makes a job go back to waiting
(the test-launch guard refuses to start a second game: exit code 9). One runner only (an OS file lock, released when the process dies). Test data is separate:
every job has its own directory with its own campaign file, bank directory and session state (GHOSTOPS_CAMPAIGN_FILE / GHOSTOPS_BANK_DIR / GHOSTOPS_SESSION_STATE).
"""
import argparse
import json
import msvcrt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import isolation  # noqa: E402

ROOT = os.path.dirname(HERE)
QDIR = os.environ.get('GHOSTOPS_QUEUE_DIR') or os.path.join(ROOT, 'tmp', 'testqueue')
QFILE = os.path.join(QDIR, 'queue.json')
LOCK = os.path.join(QDIR, 'runner.lock')
STOP = os.path.join(QDIR, 'STOP')
BEAT = os.path.join(QDIR, 'runner.json')

POLL_BUSY = 5.0        # seconds between checks while a game is running
SETTLE = 10.0          # seconds a free game must stay free before the launch
MAX_CONFLICTS = 5
ACTIVE = ('preparing', 'running')
FINAL = ('done', 'cancelled', 'error', 'interrupted')


# ---------------------------------------------------------------- injectable system facts (tests replace them)
def sc2_pids():
    import test_launch
    return test_launch.sc2_pids()


def now():
    return time.time()


def sleep(sec):
    time.sleep(sec)


def prepare_build(job):
    """Build + verify + install of the job's map (a hidden dev preset) in a FRESH process (the runner lives long: it must never run stale build code); returns 0 or a code."""
    r = subprocess.run([sys.executable, os.path.join(HERE, 'build.py'), 'prepare', '--mission', job['mission'], '--preset', job['preset']], cwd=ROOT, capture_output=True, text=True)
    try:
        os.makedirs(os.path.dirname(job['log']), exist_ok=True)
        with open(job['log'], 'a', encoding='utf-8', errors='replace') as f:
            f.write('# prepare (exit %s)' % r.returncode + chr(10) + ((r.stdout or '')[-3000:] + (r.stderr or '')[-1000:]) + chr(10))
    except OSError:
        pass
    return r.returncode


def cleanup_build(job):
    """A development map never stays in the Owner's map list (a protected map is never removed: build.uninstall_key refuses)."""
    subprocess.run([sys.executable, os.path.join(HERE, 'build.py'), 'uninstall', '--mission', job['mission'], '--preset', job['preset']], cwd=ROOT, capture_output=True, text=True)


# ---------------------------------------------------------------- queue file
def _read():
    try:
        with open(QFILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'jobs': []}


def _write(q):
    os.makedirs(QDIR, exist_ok=True)
    tmp = QFILE + '.%d.tmp' % os.getpid()
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(q, f, indent=2, ensure_ascii=False)
    os.replace(tmp, QFILE)


def update_job(job_id, **fields):
    """Atomic read-modify-write of one job (the runner, the CLI and the launcher all write this file)."""
    q = _read()
    for j in q['jobs']:
        if j['id'] == job_id:
            if j['state'] in FINAL and fields.get('state') not in (None, j['state']) and not fields.pop('_force', False):
                return j  # a finished job is never changed by a late writer
            fields.pop('_force', None)
            j.update(fields)
            j['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            _write(q)
            return j
    return None


def get_job(job_id):
    for j in _read()['jobs']:
        if j['id'] == job_id:
            return j
    return None


def enqueue(label, mission, preset, command, timeout=900):
    q = _read()
    n = 1 + max([int(j['id'][1:]) for j in q['jobs']] or [0])
    job = {'id': 'T%04d' % n, 'label': label, 'mission': mission, 'preset': preset, 'command': list(command), 'timeout': int(timeout), 'state': 'waiting',
           'phase': 'waiting for the job turn', 'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
           'conflicts': 0, 'cancel': False, 'result': '', 'log': os.path.join(QDIR, 'jobs', 'T%04d' % n, 'run.log')}
    q['jobs'].append(job)
    _write(q)
    return job


def request_cancel(job_id=None):
    """Cancels one job or all that are not finished. A waiting job is cancelled at once; a running one is stopped by the runner."""
    q = _read()
    hit = []
    for j in q['jobs']:
        if j['state'] in FINAL or (job_id and j['id'] != job_id):
            continue
        if j['state'] == 'waiting':
            j['state'], j['phase'], j['result'] = 'cancelled', 'cancelled while waiting; the game was not started', 'cancelled by command'
        else:
            j['cancel'] = True
            j['phase'] = 'cancel requested'
        j['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
        hit.append(j['id'])
    _write(q)
    return hit


def resume(job_id):
    j = get_job(job_id)
    if not j or j['state'] != 'interrupted':
        return False
    update_job(job_id, state='waiting', phase='resumed by explicit command', cancel=False, _force=True)
    return True


# ---------------------------------------------------------------- runner liveness
def runner_alive():
    """True when another runner holds the lock (the lock dies with its process, so a crashed runner never blocks)."""
    os.makedirs(QDIR, exist_ok=True)
    f = open(LOCK, 'a+')
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return True
    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    f.close()
    return False


def mark_interrupted():
    """Jobs left preparing / running by a runner that is gone: shown as interrupted, NEVER started again automatically."""
    q = _read()
    changed = False
    for j in q['jobs']:
        if j['state'] in ACTIVE:
            j['state'], j['phase'] = 'interrupted', 'the runner stopped while this job was %s: state unknown; resume or cancel explicitly' % j['state']
            j['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            changed = True
    if changed:
        _write(q)


def status(refresh=True):
    alive = runner_alive()
    if refresh and not alive:
        mark_interrupted()
    q = _read()
    return {'runner_alive': alive, 'stop_flag': os.path.exists(STOP), 'jobs': q['jobs']}


# ---------------------------------------------------------------- the runner
class Runner:
    def __init__(self, idle_exit=60.0):
        self.lock = None
        self.idle_exit = idle_exit

    def acquire(self):
        os.makedirs(QDIR, exist_ok=True)
        self.lock = open(LOCK, 'a+')
        try:
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lock.close()
            self.lock = None
            return False
        return True

    def beat(self, text=''):
        try:
            with open(BEAT, 'w', encoding='utf-8') as f:
                json.dump({'pid': os.getpid(), 'time': now(), 'text': text}, f)
        except OSError:
            pass

    def next_job(self):
        for j in _read()['jobs']:
            if j['state'] == 'waiting':
                return j
        return None

    def cancelled(self, job_id):
        j = get_job(job_id)
        return j is None or j['state'] == 'cancelled' or j.get('cancel')

    def wait_for_game(self, job):
        """True when the game is free and stayed free for SETTLE seconds; False when the job was cancelled / stop requested meanwhile."""
        free_since = None
        while True:
            j = get_job(job['id'])
            if j is None or j['state'] != 'waiting':
                return False
            if os.path.exists(STOP):
                update_job(job['id'], phase='stop flag set: this job is not started')
                return False
            pids = sc2_pids()
            if pids:
                free_since = None
                update_job(job['id'], phase='waiting for StarCraft II to be closed (running: %s); nothing is touched' % ','.join(str(p) for p in pids))
                self.beat('game busy')
                sleep(POLL_BUSY)
                continue
            if free_since is None:
                free_since = now()
                update_job(job['id'], phase='the game is free; waiting %d s and checking again' % SETTLE)
            if now() - free_since >= SETTLE:
                return True
            sleep(1.0)

    def run_job(self, job):
        jid = job['id']
        jdir = os.path.dirname(job['log'])
        os.makedirs(jdir, exist_ok=True)
        os.makedirs(os.path.join(jdir, 'banks'), exist_ok=True)
        # the last check right before the launch
        if sc2_pids():
            update_job(jid, phase='the game appeared just before the launch: back to waiting')
            return
        update_job(jid, state='preparing', phase='building and installing the dev map %s / %s' % (job['mission'], job['preset']), started=time.strftime('%Y-%m-%d %H:%M:%S'))
        try:
            rc = prepare_build(job)
        except Exception as e:  # noqa: BLE001
            rc = 'exception: %r' % (e,)
        if self.cancelled(jid):
            self.finish(job, 'cancelled', 'cancelled while preparing; the game was not started')
            return
        if rc != 0:
            self.finish(job, 'error', 'prepare failed (%s)' % rc)
            return
        if sc2_pids():
            update_job(jid, state='waiting', phase='the game appeared after the preparation: back to waiting (nothing was started)')
            self.bump_conflict(jid)
            return
        env = dict(os.environ)
        env.update({'GHOSTOPS_TEST': '1', 'GHOSTOPS_QUEUE_JOB': jid, 'GHOSTOPS_CAMPAIGN_FILE': os.path.join(jdir, 'campaign.json'),
                    'GHOSTOPS_BANK_DIR': os.path.join(jdir, 'banks'), 'GHOSTOPS_SESSION_STATE': os.path.join(jdir, 'session.json')})
        update_job(jid, state='running', phase='running the test command')
        log = open(job['log'], 'a', encoding='utf-8', errors='replace')
        log.write('# job %s %s\n# command: %s\n' % (jid, job['label'], job['command']))
        log.flush()
        proc = subprocess.Popen(job['command'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        t0 = now()
        reason = None
        while proc.poll() is None:
            self.beat('running %s' % jid)
            if self.cancelled(jid):
                reason = 'cancelled'
                break
            if now() - t0 > job['timeout']:
                reason = 'timeout'
                break
            sleep(1.0)
        if reason:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)  # our own test script (and what it started), never a game by name
        rc = proc.poll() if not reason else None
        log.close()
        self.close_own_game(jid)
        try:
            cleanup_build(job)
        except Exception:  # noqa: BLE001
            pass
        if reason == 'cancelled':
            self.finish(job, 'cancelled', 'cancelled while running; only the test game of this job was closed')
        elif reason == 'timeout':
            self.finish(job, 'error', 'time limit %d s exceeded; the test was stopped, only its own game was closed' % job['timeout'])
        elif rc == 9:
            update_job(jid, state='waiting', phase='a game appeared at the moment of the launch (exit 9): back to waiting')
            self.bump_conflict(jid)
        elif rc == 0:
            self.finish(job, 'done', 'finished: exit code 0 (the log has the details)')
        else:
            self.finish(job, 'error', 'the test command exited with code %s (see the log)' % rc)

    def bump_conflict(self, jid):
        j = get_job(jid)
        n = (j or {}).get('conflicts', 0) + 1
        update_job(jid, conflicts=n)
        if n >= MAX_CONFLICTS:
            self.finish(j, 'error', 'the game kept appearing: %d conflicts, the job was given up (nothing was closed)' % n)

    def close_own_game(self, jid):
        for pid in sc2_pids():
            if isolation.is_owned(pid, jid):
                isolation.close_owned(pid, jid)

    def finish(self, job, state, text):
        update_job(job['id'], state=state, phase=text, result=text, finished=time.strftime('%Y-%m-%d %H:%M:%S'), _force=False)

    def loop(self):
        if not self.acquire():
            print('another runner is active: this one exits')
            return 3
        mark_interrupted()
        idle_since = now()
        try:
            while True:
                self.beat('idle')
                if os.path.exists(STOP):
                    print('stop flag: no further job is started')
                    return 0
                job = self.next_job()
                if job is None:
                    if now() - idle_since > self.idle_exit:
                        return 0
                    sleep(1.0)
                    continue
                idle_since = now()
                if not self.wait_for_game(job):
                    continue
                self.run_job(get_job(job['id']))
        finally:
            try:
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass


def start_detached():
    """Starts the runner outside this process tree (it must outlive the conversation); nothing happens when one is alive."""
    if runner_alive():
        return False
    pyw = sys.executable.replace('python.exe', 'pythonw.exe')
    cmd = '"%s" "%s" run' % (pyw if os.path.exists(pyw) else sys.executable, os.path.abspath(__file__))
    ps = "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = '%s'; CurrentDirectory = '%s' } | Out-Null" % (cmd.replace("'", "''"), ROOT)
    subprocess.run(['powershell', '-NoProfile', '-Command', ps])
    return True


def format_status(st):
    lines = ['runner: %s%s' % ('active' if st['runner_alive'] else 'not running', ', stop flag set' if st['stop_flag'] else '')]
    for j in st['jobs'][-12:]:
        lines.append('%s  %-11s %s  [%s / %s]  %s' % (j['id'], j['state'], j['label'], j['mission'], j['preset'], j['phase']))
        if j['state'] in FINAL:
            lines.append('      log: %s' % j['log'])
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='c', required=True)
    s = sub.add_parser('enqueue')
    s.add_argument('--label', required=True)
    s.add_argument('--mission', required=True)
    s.add_argument('--preset', required=True)
    s.add_argument('--timeout', type=int, default=900)
    s.add_argument('--no-start', action='store_true')
    s.add_argument('command', nargs=argparse.REMAINDER)
    s = sub.add_parser('status')
    s.add_argument('--json', action='store_true')
    s = sub.add_parser('cancel')
    s.add_argument('job', nargs='?')
    s.add_argument('--all', action='store_true')
    sub.add_parser('stop')
    sub.add_parser('go')
    s = sub.add_parser('resume')
    s.add_argument('job')
    sub.add_parser('start')
    sub.add_parser('run')
    a = p.parse_args(argv)
    if a.c == 'enqueue':
        cmd = [c for c in a.command if c != '--']
        if not cmd:
            print('no command')
            return 2
        job = enqueue(a.label, a.mission, a.preset, cmd, a.timeout)
        if not a.no_start:
            start_detached()
        print('queued', job['id'])
        return 0
    if a.c == 'status':
        st = status()
        print(json.dumps(st, indent=2, ensure_ascii=False) if a.json else format_status(st))
        return 0
    if a.c == 'cancel':
        hit = request_cancel(None if a.all or not a.job else a.job)
        print('cancel requested for', hit or 'nothing')
        return 0
    if a.c == 'stop':
        os.makedirs(QDIR, exist_ok=True)
        open(STOP, 'w').close()
        print('stop flag set')
        return 0
    if a.c == 'go':
        if os.path.exists(STOP):
            os.remove(STOP)
        start_detached()
        print('stop flag removed')
        return 0
    if a.c == 'resume':
        print('resumed' if resume(a.job) else 'nothing to resume')
        start_detached()
        return 0
    if a.c == 'start':
        print('runner started' if start_detached() else 'a runner is already active')
        return 0
    return Runner().loop()


if __name__ == '__main__':
    sys.exit(main())
