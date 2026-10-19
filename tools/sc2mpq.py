"""Minimal MPQ reader/writer for StarCraft II maps (stdlib only).

Own implementation. The reader and the sector packer descend from the helper scripts
used for the Hammer of Dawn localisation fix (accepted by the 3.1.4 client).

Scope: read files; replace, add or remove files while keeping every other block
byte-for-byte; create small archives from scratch (used by the tests).
Not supported: encrypted files, archives with a hash table that has no free slot.
"""
import struct
import zlib
import bz2

M32 = 0xFFFFFFFF
EMPTY_HASH = (M32, M32, 0xFFFF, 0xFFFF, M32)
DELETED = 0xFFFFFFFE
FLAG_EXISTS = 0x80000000
FLAG_COMPRESS = 0x00000200
FLAG_IMPLODE = 0x00000100
FLAG_SINGLE = 0x01000000
FLAG_ENCRYPTED = 0x00010000


def _make_table():
    t = [0] * 0x500
    seed = 0x00100001
    for i in range(0x100):
        idx = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            a = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            b = seed & 0xFFFF
            t[idx] = a | b
            idx += 0x100
    return t


T = _make_table()


def name_hash(name, kind):
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for c in name.upper().replace('/', '\\').encode('latin1'):
        v = T[(kind << 8) + c]
        s1 = (v ^ (s1 + s2)) & M32
        s2 = (c + s1 + s2 + (s2 << 5) + 3) & M32
    return s1


def decrypt(data, key):
    out = bytearray()
    s2 = 0xEEEEEEEE
    for i in range(0, len(data) // 4 * 4, 4):
        s2 = (s2 + T[0x400 + (key & 0xFF)]) & M32
        v = struct.unpack_from('<I', data, i)[0]
        v = (v ^ (key + s2)) & M32
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & M32
        s2 = (v + s2 + (s2 << 5) + 3) & M32
        out += struct.pack('<I', v)
    return bytes(out)


def encrypt(data, key):
    out = bytearray()
    s2 = 0xEEEEEEEE
    for i in range(0, len(data), 4):
        s2 = (s2 + T[0x400 + (key & 0xFF)]) & M32
        v = struct.unpack_from('<I', data, i)[0]
        out += struct.pack('<I', (v ^ (key + s2)) & M32)
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & M32
        s2 = (v + s2 + (s2 << 5) + 3) & M32
    return bytes(out)


def pack_file(data, sector_size):
    """Sectored zlib packing; a sector stays raw when compression does not help."""
    n = max(1, (len(data) + sector_size - 1) // sector_size)
    segs = []
    for k in range(n):
        chunk = data[k * sector_size:(k + 1) * sector_size]
        c = b'\x02' + zlib.compress(chunk, 9)
        segs.append(c if len(c) < len(chunk) else chunk)
    offs = [4 * (n + 1)]
    for s in segs:
        offs.append(offs[-1] + len(s))
    return struct.pack('<%dI' % (n + 1), *offs) + b''.join(segs)


class MPQError(Exception):
    pass


class Archive:
    def __init__(self, data):
        d = bytes(data)
        self.base = 0
        if d[:4] == b'MPQ\x1b':
            self.base = struct.unpack_from('<I', d, 8)[0]
        b = self.base
        if d[b:b + 4] != b'MPQ\x1a':
            raise MPQError('no MPQ header')
        self.prefix = d[:b]
        _hs, _asz, ver, shift, hpos, bpos, hcnt, bcnt = struct.unpack_from('<IIHHIIII', d, b + 4)
        if ver >= 1:
            hh, bh = struct.unpack_from('<HH', d, b + 0x28)
            hpos |= hh << 32
            bpos |= bh << 32
        self.version = ver
        self.sector_size = 512 << shift
        ht = decrypt(d[b + hpos:b + hpos + hcnt * 16], name_hash('(hash table)', 3))
        bt = decrypt(d[b + bpos:b + bpos + bcnt * 16], name_hash('(block table)', 3))
        self.hashes = [list(struct.unpack_from('<IIHHI', ht, i * 16)) for i in range(hcnt)]
        self.blocks = []
        for i in range(bcnt):
            off, csz, fsz, fl = struct.unpack_from('<IIII', bt, i * 16)
            raw = d[b + off:b + off + csz] if fl & FLAG_EXISTS else b''
            if fl & FLAG_ENCRYPTED:
                raise MPQError('encrypted block %d is not supported' % i)
            self.blocks.append([raw, fsz, fl])

    # ---- lookup -------------------------------------------------------
    def _slot(self, name):
        a, b2 = name_hash(name, 1), name_hash(name, 2)
        n = len(self.hashes)
        i = name_hash(name, 0) & (n - 1)
        for _ in range(n):
            e = self.hashes[i]
            if e[4] == M32 and e[0] == M32:
                return None
            if e[0] == a and e[1] == b2 and e[4] != DELETED:
                return i
            i = (i + 1) & (n - 1)
        return None

    def has(self, name):
        return self._slot(name) is not None

    def _unc(self, buf, size):
        if len(buf) == size:
            return buf
        m = buf[0]
        p = buf[1:]
        if m & 0x10:
            p = bz2.decompress(p)
            m &= ~0x10
        elif m & 0x02:
            p = zlib.decompress(p)
            m &= ~0x02
        if m:
            raise MPQError('unsupported compression 0x%x' % m)
        return p

    def read(self, name):
        s = self._slot(name)
        if s is None:
            return None
        raw, fsz, fl = self.blocks[self.hashes[s][4]]
        if not fl & (FLAG_COMPRESS | FLAG_IMPLODE):
            return raw
        if fl & FLAG_SINGLE:
            return self._unc(raw, fsz)
        ss = self.sector_size
        n = (fsz + ss - 1) // ss
        offs = struct.unpack_from('<%dI' % (n + 1), raw, 0)
        out = []
        for k in range(n):
            out.append(self._unc(raw[offs[k]:offs[k + 1]], min(ss, fsz - k * ss)))
        return b''.join(out)

    def names(self):
        lf = self.read('(listfile)')
        if not lf:
            return []
        return [x for x in lf.decode('latin1').replace('\r\n', '\n').split('\n') if x]

    # ---- modification -------------------------------------------------
    def set_file(self, name, data):
        raw = pack_file(data, self.sector_size)
        entry = [raw, len(data), FLAG_EXISTS | FLAG_COMPRESS]
        s = self._slot(name)
        if s is not None:
            self.blocks[self.hashes[s][4]] = entry
            return
        n = len(self.hashes)
        i = name_hash(name, 0) & (n - 1)
        for _ in range(n):
            e = self.hashes[i]
            if e[4] in (M32, DELETED):
                self.blocks.append(entry)
                self.hashes[i] = [name_hash(name, 1), name_hash(name, 2), 0, 0, len(self.blocks) - 1]
                return
            i = (i + 1) & (n - 1)
        raise MPQError('hash table is full')

    def remove(self, name):
        s = self._slot(name)
        if s is not None:
            self.hashes[s][4] = DELETED

    def update_listfile(self, extra_names):
        have = self.names()
        merged = list(have)
        for n in extra_names:
            if n not in merged:
                merged.append(n)
        if merged != have and self.has('(listfile)'):
            self.set_file('(listfile)', ('\r\n'.join(merged) + '\r\n').encode('latin1'))

    def drop_attributes(self):
        """(attributes) holds one CRC per block; it is optional, so drop it after edits."""
        self.remove('(attributes)')

    # ---- serialisation ------------------------------------------------
    def tobytes(self):
        pos = 44
        body = bytearray()
        table = []
        for raw, fsz, fl in self.blocks:
            if fl & FLAG_EXISTS:
                table.append((pos + len(body), len(raw), fsz, fl))
                body += raw
            else:
                table.append((0, 0, fsz, fl))
        hpos = pos + len(body)
        ht = encrypt(b''.join(struct.pack('<IIHHI', *e) for e in self.hashes),
                     name_hash('(hash table)', 3))
        bpos = hpos + len(ht)
        bt = encrypt(b''.join(struct.pack('<IIII', *e) for e in table),
                     name_hash('(block table)', 3))
        total = bpos + len(bt)
        shift = (self.sector_size // 512).bit_length() - 1
        hdr = struct.pack('<4sIIHHIIIIQHH', b'MPQ\x1a', 44, total, 1, shift, hpos, bpos,
                          len(self.hashes), len(table), 0, 0, 0)
        return self.prefix + hdr + bytes(body) + ht + bt


def create(files, sector_size=4096):
    """Build a fresh archive from {name: bytes}. A (listfile) is added."""
    names = list(files)
    count = len(names) + 1
    size = 16
    while size < count * 2:
        size *= 2
    a = Archive.__new__(Archive)
    a.base = 0
    a.prefix = b''
    a.version = 1
    a.sector_size = sector_size
    a.hashes = [list(EMPTY_HASH) for _ in range(size)]
    a.blocks = []
    for n in names:
        a.set_file(n, files[n])
    a.set_file('(listfile)', ('\r\n'.join(names) + '\r\n').encode('latin1'))
    return a.tobytes()
