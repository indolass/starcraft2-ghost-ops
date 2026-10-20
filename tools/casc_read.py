r"""Read-only helper for local research: list / read files of the installed game's CASC (see docs/EXTRACT_MAP.md for the CascLib DLL).
Nothing is written into the game install; extracted data stays in git-ignored tmp/.

  python tools/casc_read.py --list "mods\liberty.sc2mod\base.sc2data\gamedata\*"
  python tools/casc_read.py --get "mods\liberty.sc2mod\base.sc2data\gamedata\modeldata.xml" tmp/casc/modeldata.xml
"""
import argparse
import ctypes as c
import os
import sys


def open_lib(casc, storage):
    lib = c.CDLL(casc)
    P, U, B = c.c_void_p, c.c_uint32, c.c_char_p

    def fn(name, args, ret=c.c_bool):
        f = getattr(lib, name)
        f.argtypes, f.restype = args, ret
        return f
    api = {'open_store': fn('CascOpenStorage', [B, U, c.POINTER(P)]), 'open_file': fn('CascOpenFile', [P, B, U, U, c.POINTER(P)]),
           'read': fn('CascReadFile', [P, P, U, c.POINTER(U)]), 'close_file': fn('CascCloseFile', [P]), 'close_store': fn('CascCloseStorage', [P]),
           'find_first': fn('CascFindFirstFile', [P, B, P, B], P), 'find_next': fn('CascFindNextFile', [P, P]), 'find_close': fn('CascFindClose', [P])}
    store = P()
    if not api['open_store'](storage.encode(), 0, c.byref(store)):
        raise SystemExit('CascOpenStorage failed')
    return api, store


def list_files(api, store, pattern, limit=100000):
    P = c.c_void_p
    data = c.create_string_buffer(65536)
    h = api['find_first'](store, pattern.encode(), data, None)
    out = []
    if not h or h == P(-1).value:
        return out
    while len(out) < limit:
        out.append(data.value.decode('utf-8', 'replace'))
        if not api['find_next'](h, data):
            break
    api['find_close'](h)
    return out


def read_file(api, store, name):
    P, U = c.c_void_p, c.c_uint32
    f = P()
    if not api['open_file'](store, name.encode(), 0, 0, c.byref(f)):
        raise SystemExit('cannot open %s' % name)
    buf = c.create_string_buffer(1 << 20)
    n = U()
    parts = []
    while True:
        if not api['read'](f, buf, len(buf), c.byref(n)):
            raise SystemExit('read failed')
        if not n.value:
            break
        parts.append(buf.raw[:n.value])
    api['close_file'](f)
    return b''.join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--casc', default='tmp/thirdparty/casc.dll')
    ap.add_argument('--storage', default=r'E:\Games\StarCraft II')
    ap.add_argument('--list')
    ap.add_argument('--get', nargs=2, metavar=('PATH', 'OUT'))
    a = ap.parse_args(argv)
    api, store = open_lib(a.casc, a.storage)
    if a.list:
        for n in list_files(api, store, a.list):
            print(n)
    if a.get:
        data = read_file(api, store, a.get[0])
        os.makedirs(os.path.dirname(os.path.abspath(a.get[1])), exist_ok=True)
        open(a.get[1], 'wb').write(data)
        print('wrote', a.get[1], len(data))
    api['close_store'](store)


if __name__ == '__main__':
    sys.exit(main())
