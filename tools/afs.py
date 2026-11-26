#!/usr/bin/env python3
"""CRI AFS archive reader / writer.

Layout (all Namida archives): 'AFS\\0', u32 n, n x (u32 offset, u32 size), (u32 nt_off, u32 nt_size),
files at 0x800-aligned offsets starting at the header end rounded up, then the name table
(n x 48 bytes: name[32], 6 x u16 date, u32 = n) at the next 0x800 boundary, file padded to 0x800.

usage: afs.py list ARCHIVE | afs.py extract ARCHIVE OUTDIR
library: read_afs(path) -> [(i, name, off, size)];  Afs(path).data(i), .meta(i);  build(entries) -> bytes
"""
import struct, sys, os

ALIGN = 0x800


def _up(x, a=ALIGN): return (x + a - 1) // a * a


def read_afs(path):
    with open(path, 'rb') as f:
        data = f.read(0x80000)
        assert data[:4] == b'AFS\0', 'not AFS'
        n = struct.unpack_from('<I', data, 4)[0]
        need = 8 + n * 8 + 8
        if need > len(data):
            f.seek(0); data = f.read(need)
        ents = [struct.unpack_from('<II', data, 8 + i * 8) for i in range(n)]
        nt_off, nt_size = struct.unpack_from('<II', data, 8 + n * 8)
        names = []
        if nt_off and nt_size:
            f.seek(nt_off); nt = f.read(nt_size)
            for i in range(n):
                e = nt[i * 48:(i + 1) * 48]
                names.append(e[:32].split(b'\0')[0].decode('ascii', 'replace') if len(e) == 48 else f'{i:05d}.bin')
        else:
            names = [f'{i:05d}.bin' for i in range(n)]
    return [(i, names[i], o, s) for i, (o, s) in enumerate(ents)]


class Afs:
    """Random access to an archive's members and their 48-byte name-table records."""
    def __init__(self, path):
        self.path = path; self.ents = read_afs(path)
        n = len(self.ents)
        with open(path, 'rb') as f:
            f.seek(8 + 8 * n); nt_off, nt_size = struct.unpack('<II', f.read(8))
            f.seek(nt_off); self.nt = f.read(nt_size)
        self.names = [e[1] for e in self.ents]

    def data(self, i):
        _, _, o, s = self.ents[i]
        with open(self.path, 'rb') as f:
            f.seek(o); return f.read(s)

    def meta(self, i):
        return self.nt[i * 48:(i + 1) * 48]

    def index(self, name):
        return self.names.index(name)


def build(members, metas):
    """members: list of bytes; metas: list of 48-byte name records (size field kept as stored)."""
    n = len(members)
    pos = _up(8 + 8 * n + 8)
    offs = []
    for m in members:
        offs.append(pos); pos = _up(pos + len(m))
    nt = b''.join(metas)
    nt_off = pos; end = _up(nt_off + len(nt))
    out = bytearray(end)
    out[0:8] = b'AFS\0' + struct.pack('<I', n)
    for i, (o, m) in enumerate(zip(offs, members)):
        struct.pack_into('<II', out, 8 + 8 * i, o, len(m))
        out[o:o + len(m)] = m
    struct.pack_into('<II', out, 8 + 8 * n, nt_off, len(nt))
    out[nt_off:nt_off + len(nt)] = nt
    return bytes(out)


if __name__ == '__main__':
    cmd, arc = sys.argv[1], sys.argv[2]
    ents = read_afs(arc)
    if cmd == 'list':
        for i, nm, o, s in ents:
            print(f'{i:5d} {o:#010x} {s:10d} {nm}')
    elif cmd == 'extract':
        out = sys.argv[3]; os.makedirs(out, exist_ok=True)
        with open(arc, 'rb') as f:
            for i, nm, o, s in ents:
                f.seek(o)
                with open(os.path.join(out, f'{i:04d}_{nm}'), 'wb') as g:
                    g.write(f.read(s))
