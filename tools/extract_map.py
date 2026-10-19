"""Extract one original campaign map from the installed game (CASC, read only) into an .SC2Map.

Needs a locally built CascLib (MIT, https://github.com/ladislav-zezula/CascLib) as a DLL; see
docs/EXTRACT_MAP.md. Only the files of the requested map are read; the game install is never
written. Packing uses tools/sc2mpq.py.

  python tools/extract_map.py --casc tmp/thirdparty/casc.dll --mission traynor02 \
      --storage "E:\\Games\\StarCraft II" --out tmp/source/TRaynor02.SC2Map
"""
import argparse
import ctypes as c
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc2mpq  # noqa: E402

KEEP_LOCALES = {'base.sc2data', 'enus.sc2data', 'ruru.sc2data'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--casc', required=True)
    ap.add_argument('--storage', default=r'E:\Games\StarCraft II')
    ap.add_argument('--mission', default='traynor02')
    ap.add_argument('--campaign', default='liberty')
    ap.add_argument('--out', required=True)
    ap.add_argument('--list-only', action='store_true')
    a = ap.parse_args(argv)
    if not a.mission.isalnum():
        raise SystemExit('mission must be alphanumeric')
    lib = c.CDLL(a.casc)
    P, U, B = c.c_void_p, c.c_uint32, c.c_char_p

    def fn(name, args, ret=c.c_bool):
        f = getattr(lib, name)
        f.argtypes, f.restype = args, ret
        return f
    open_store = fn('CascOpenStorage', [B, U, c.POINTER(P)])
    open_file = fn('CascOpenFile', [P, B, U, U, c.POINTER(P)])
    read = fn('CascReadFile', [P, P, U, c.POINTER(U)])
    close_file = fn('CascCloseFile', [P])
    close_store = fn('CascCloseStorage', [P])
    find_first = fn('CascFindFirstFile', [P, B, P, B], P)
    find_next = fn('CascFindNextFile', [P, P])
    find_close = fn('CascFindClose', [P])

    store = P()
    if not open_store(a.storage.encode(), 0, c.byref(store)):
        raise SystemExit('CascOpenStorage failed, last error %d' % c.get_last_error() if hasattr(c, 'get_last_error') else 'CascOpenStorage failed')
    prefix = ('campaigns\\%s.sc2campaign\\base.sc2maps\\maps\\campaign\\%s.sc2map\\' % (a.campaign, a.mission)).encode()
    data = c.create_string_buffer(65536)
    h = find_first(store, prefix + b'*', data, None)
    if not h or h == P(-1).value:
        raise SystemExit('no files found under %s' % prefix.decode())
    names = []
    while True:
        names.append(data.value)
        if not find_next(h, data):
            break
    find_close(h)
    print('found %d entries' % len(names))
    files = {}
    for name in names:
        rel = name[len(prefix):]
        first = rel.split(b'\\')[0].lower()
        if first.endswith(b'.sc2data') and first.decode() not in KEEP_LOCALES:
            continue
        if a.list_only:
            print(' ', rel.decode())
            continue
        f = P()
        if not open_file(store, name, 0, 0, c.byref(f)):
            raise SystemExit('cannot open %s' % name.decode())
        buf = c.create_string_buffer(1 << 20)
        n = U()
        parts = []
        while True:
            if not read(f, buf, len(buf), c.byref(n)):
                raise SystemExit('read failed for %s' % name.decode())
            if not n.value:
                break
            parts.append(buf.raw[:n.value])
        close_file(f)
        files[rel.decode()] = b''.join(parts)
    close_store(store)
    if a.list_only:
        return 0
    if os.path.exists(a.out):
        raise SystemExit('refusing to overwrite %s' % a.out)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'wb') as f:
        f.write(sc2mpq.create(files))
    print('wrote %s: %d components, %d bytes' % (a.out, len(files), os.path.getsize(a.out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
