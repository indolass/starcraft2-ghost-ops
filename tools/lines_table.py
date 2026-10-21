"""Ghost Ops shared lines table: ONE small JSON file per mission (and per profile) that both Voice Studio and the game build read.  stdlib only.

This single file is the whole contract implementation: copy it unchanged next to the build (tools/lines_table.py) to read the texts, to mark that the build
read the table (honest status in the studio) and to apply the texts to a config before the profile merge. Nothing here knows about events, conditions, timings or
mission logic: those stay in the game project. The table holds only the words.

File: <lines_dir>/<mission>[.<variant>].lines.json
{
 "schema": "ghostops.lines/1", "mission_id": "traynor03", "variant": "defence" | null, "title": "...", "order": 30,
 "table_rev": 12,                              # +1 on every write (informational)
 "languages": ["ru", "en"],
 "speakers": {"raynor": "Джим Рейнор", ...},
 "scenes": [{"id", "title", "context", "group"}],           # in playthrough order
 "consumers": {"game": {"read_utc", "table_rev", "tool"}},  # written by the game build through mark_game_read(); absent = the game side is NOT connected
 "lines": [{
   "id": "RAYNOR_INFECT",                      # stable id (existing ids are kept)
   "key": "traynor02/RAYNOR_INFECT",           # mission[/variant]/id, unique
   "speaker": "raynor", "scene": "S3_...", "order": 30, "context": "...", "condition": "...", "route": "main"|"variant",
   "mode": "record" | "game_clip" | "game_native" | "text_only",    # Owner records / ready game clip / original game dialogue / only text
   "text": {"ru": "...", "en": "..."},         # THE shared text (the only editable content)
   "origin_text": {"ru": "...", "en": "..."},  # the agreed text at seeding; never changed (the studio can restore it)
   "hash": "sha256 of the normalised text map", "rev": 3, "edited_by": "studio" | "game" | "seed", "edited_utc": "...",
   "binding": {"config": "traynor03.json", "path": "presets.defence.overrides.defence.texts.RaynorText"},   # where the game config keeps this text (raw config path)
   "clip": {"id": "GhostOps...", "main_asset": "assets/audio/traynor03/x.wav"}                              # game_clip lines only (informational)
 }]
}
Writes: update_text() locks the file, compares the CURRENT text of that line and language with the text the writer started from (compare and swap) and replaces the file
atomically; a different line or language never conflicts; a stale snapshot is never written over somebody else's change. Paths: get_path / set_path understand dotted
keys and [id=X] selectors. Command line (read only): python lines_table.py check <lines_dir> <game project dir>  -> differences between the tables and the configs.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import tempfile
import time

SCHEMA = 'ghostops.lines/1'
MODES = ('record', 'game_clip', 'game_native', 'text_only')


def norm_text(t):
    t = (t or '').replace('…', '...').replace('—', '-').replace('–', '-').replace(' ', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def text_hash(text_map):
    """Hash of the editable content: the normalised text of every language."""
    canon = json.dumps({k: norm_text(v) for k, v in sorted((text_map or {}).items())}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def table_filename(mission_id, variant=None):
    return '%s%s.lines.json' % (mission_id, ('.' + variant) if variant else '')


def table_path(lines_dir, mission_id, variant=None):
    return os.path.join(lines_dir, table_filename(mission_id, variant))


def line_key(mission_id, variant, line_id):
    return '/'.join(x for x in (mission_id, variant, line_id) if x)


# ---------------------------------------------------------------- reading
def read_table(path, retries=6):
    """Read and normalise a table. Returns the dict (lines carry `hash_ok`: False when the text was edited by hand without updating `hash`). Raises OSError/ValueError."""
    last = None
    for i in range(retries):
        try:
            with open(path, encoding='utf-8') as f:
                t = json.load(f)
            break
        except (ValueError, PermissionError) as ex:   # a writer is replacing the file just now (Windows: sharing violation) / half-written copy: retry shortly
            last = ex
            time.sleep(0.03 * (i + 1))
    else:
        if isinstance(last, PermissionError):
            raise last
        raise ValueError('table is not valid JSON: %s' % last)
    if t.get('schema') != SCHEMA:
        raise ValueError('unknown table schema %r' % t.get('schema'))
    for ln in t.get('lines', []):
        real = text_hash(ln.get('text'))
        ln['hash_ok'] = ln.get('hash') == real
        ln['hash'] = real                     # the content hash is always computed from the text (hand edits are therefore seen as changes)
    return t


def line_index(table):
    return {ln['id']: ln for ln in table.get('lines', [])}


def texts_for_build(lines_dir, mission_id, variant=None):
    """{line id: {'ru': .., 'en': ..}} for the game build."""
    t = read_table(table_path(lines_dir, mission_id, variant))
    return {ln['id']: dict(ln['text']) for ln in t['lines']}


# ---------------------------------------------------------------- locking and atomic writing
@contextlib.contextmanager
def file_lock(path, timeout=10.0, stale=30.0):
    """Cross-process lock: <path>.lock created exclusively; a lock older than `stale` seconds is taken over."""
    lock = path + '.lock'
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ('%d %s' % (os.getpid(), utcnow())).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.time() - t0 > timeout:
                raise TimeoutError('lines table is locked by another process: %s' % lock)
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _atomic_write(path, table):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.lines_', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(_for_disk(table), f, ensure_ascii=False, indent=1)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        for i in range(60):                      # Windows: a reader that has the file open makes the replace fail for a moment
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if i == 59:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _for_disk(table):
    out = dict(table)
    out['lines'] = [{k: v for k, v in ln.items() if k != 'hash_ok'} for ln in table.get('lines', [])]
    return out


def write_new_table(path, table):
    """Create (or replace) a whole table: used by the seeding tool only. Takes the lock."""
    table = json.loads(json.dumps(table))
    table.setdefault('schema', SCHEMA)
    table['table_rev'] = int(table.get('table_rev', 0)) + 1
    for ln in table.get('lines', []):
        ln['hash'] = text_hash(ln.get('text'))
        ln.setdefault('rev', 1)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with file_lock(path):
        _atomic_write(path, table)


NO_CHECK = object()


def update_text(path, line_id, lang, new_text, expected=NO_CHECK, edited_by='studio'):
    """Compare-and-swap edit of ONE line's text in ONE language. `expected` = the text of that language the editor started from (the base of the edit; None = the language
    was absent; NO_CHECK = unconditional). Texts of other languages and other lines never take part in the check, so they never conflict.
    Returns {'status': 'ok'|'unchanged'|'conflict'|'missing', 'line': <line dict as now in the file>}; nothing is written unless status == 'ok'.
    The whole read-modify-write happens under the lock and the file is replaced atomically, so a change made by another process is never overwritten by an old snapshot."""
    with file_lock(path):
        t = read_table(path)
        ln = line_index(t).get(line_id)
        if ln is None:
            return {'status': 'missing', 'line': None}
        cur = ln['text'].get(lang)
        if norm_text(cur) == norm_text(new_text):
            return {'status': 'unchanged', 'line': ln}
        if expected is not NO_CHECK and norm_text(cur) != norm_text(expected):
            return {'status': 'conflict', 'line': ln}
        ln['text'][lang] = (new_text or '').strip()          # stored as given (typography is kept); every comparison and the hash use norm_text
        ln['hash'] = text_hash(ln['text'])
        ln['rev'] = int(ln.get('rev', 1)) + 1
        ln['edited_by'] = edited_by
        ln['edited_utc'] = utcnow()
        # other lines edited by hand since the last write keep their text; their hashes are refreshed so that nobody sees them as changed forever
        for other in t['lines']:
            if not other.get('hash_ok', True):
                other['rev'] = int(other.get('rev', 1)) + 1
                other['edited_by'] = other.get('edited_by') or 'hand'
        t['table_rev'] = int(t.get('table_rev', 0)) + 1
        _atomic_write(path, t)
        return {'status': 'ok', 'line': ln}


def mark_game_read(path, tool='build', info=None):
    """The game build calls this after it READ the table: the studio then shows 'the game reads the shared table' (and which revision). Only touches header.consumers.
    Does not rewrite the file when the same tool already recorded the same revision. Returns True if it wrote."""
    with file_lock(path):
        t = read_table(path)
        old = (t.get('consumers') or {}).get('game') or {}
        if old.get('table_rev') == t.get('table_rev') and old.get('tool') == tool and all(old.get(k) == v for k, v in (info or {}).items()):
            return False
        t.setdefault('consumers', {})['game'] = dict(info or {}, read_utc=utcnow(), table_rev=t.get('table_rev'), tool=tool)
        _atomic_write(path, t)
        return True


# ---------------------------------------------------------------- config paths (raw game config) and applying texts
_TOKEN = re.compile(r'([^.\[\]]+)|\[([^\]]+)\]')


def _tokens(path):
    for m in _TOKEN.finditer(path):
        yield (m.group(1), None) if m.group(1) else (None, m.group(2))


def get_path(doc, path):
    cur = doc
    for key, sel in _tokens(path):
        if key is not None:
            cur = cur[key]
        elif '=' in sel:
            k, v = sel.split('=', 1)
            cur = next(x for x in cur if isinstance(x, dict) and str(x.get(k)) == v)
        else:
            cur = cur[int(sel)]
    return cur


def set_path(doc, path, value):
    toks = list(_tokens(path))
    cur = doc
    for key, sel in toks[:-1]:
        cur = cur[key] if key is not None else (next(x for x in cur if isinstance(x, dict) and str(x.get(sel.split('=', 1)[0])) == sel.split('=', 1)[1]) if '=' in sel else cur[int(sel)])
    key, sel = toks[-1]
    cur[key] = value


def apply_texts_to_config(cfg, table, config_name=None):
    """Put the table's texts into the RAW config dict (call it right after json.load and BEFORE the preset merge). Returns {'applied': [ids], 'skipped': [(id, reason)]}.
    Only lines with a binding whose config file name matches `config_name` (if given) and whose mode is not game_native are applied; text dicts keep their other keys."""
    applied, skipped = [], []
    for ln in table.get('lines', []):
        b = ln.get('binding')
        if not b or ln.get('mode') == 'game_native':
            continue
        if config_name and os.path.basename(b.get('config', '')) != os.path.basename(config_name):
            continue
        try:
            cur = get_path(cfg, b['path'])
        except (KeyError, StopIteration, IndexError, TypeError):
            skipped.append((ln['id'], 'binding path not found'))
            continue
        if not isinstance(cur, dict):
            skipped.append((ln['id'], 'binding does not point at a text object'))
            continue
        new = dict(cur)
        new.update({k: v for k, v in ln['text'].items() if v})
        if new != cur:
            cur.clear(); cur.update(new)
        applied.append(ln['id'])
    return {'applied': applied, 'skipped': skipped}


# ---------------------------------------------------------------- command line: drift report (read only)
def check_against_project(lines_dir, project_dir):
    """Compare every bound text of every table in `lines_dir` with the config files of the game project. Returns a list of (table key, language, table text, config text)."""
    out, cfgs = [], {}
    for name in sorted(os.listdir(lines_dir)):
        if not name.endswith('.lines.json') or name.startswith('.'):
            continue
        t = read_table(os.path.join(lines_dir, name))
        for ln in t['lines']:
            b = ln.get('binding')
            if not b:
                continue
            if b['config'] not in cfgs:
                with open(os.path.join(project_dir, 'config', b['config']), encoding='utf-8') as f:
                    cfgs[b['config']] = json.load(f)
            try:
                cur = get_path(cfgs[b['config']], b['path'])
            except (KeyError, StopIteration, IndexError, TypeError):
                out.append((ln['key'], '-', '(binding path found nowhere)', b['path']))
                continue
            for lang, txt in ln['text'].items():
                if norm_text(txt) != norm_text((cur or {}).get(lang)):
                    out.append((ln['key'], lang, txt, (cur or {}).get(lang)))
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == 'check':
        rows = check_against_project(sys.argv[2], sys.argv[3])
        for key, lang, a, b in rows:
            print('DIFF %s [%s]\n  table : %s\n  config: %s' % (key, lang, a, b))
        print('%d difference(s) between the shared tables and the project configs (read only)' % len(rows))
        sys.exit(1 if rows else 0)
    print('usage: python lines_table.py check <lines_dir> <game project dir>')
    sys.exit(2)
