#!/usr/bin/env python3
"""Patch files inside the Namida DVD image (ISO9660 + UDF 1.02 bridge) without changing its size.

A replacement that fits the file's old sector count stays in place (tail zeroed).
A larger one is moved to the front of /PADDING/PADD00.BIN, whose start is pushed forward
and size reduced, so no extents overlap. Both the ISO9660 directory record and the UDF
File Entry (short_ad + information length + tag CRC) are updated; the PS2 reads ISO9660.

usage: iso.py list ISO | iso.py put ISO_IN ISO_OUT /PATH=localfile [...]
library: Disc(f).files -> {path: File};  patch(iso_in, iso_out, {path: bytes})
"""
import struct, sys, os, shutil

SEC = 2048
PAD = '/PADDING/PADD00.BIN'


def both32(v): return struct.pack('<I', v) + struct.pack('>I', v)


def crc_ccitt(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class File:
    def __init__(self, path, lba, size, iso_rec):
        self.path, self.lba, self.size, self.iso_rec = path, lba, size, iso_rec
        self.udf_fe = None          # absolute byte offset of the UDF File Entry


class Disc:
    def __init__(self, f):
        self.f = f; self.files = {}
        f.seek(16 * SEC); pvd = f.read(SEC); root = pvd[156:190]
        self._iso_dir(struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0], '')
        self._udf()

    def read(self, sec, n=SEC):
        self.f.seek(sec * SEC); return self.f.read(n)

    def _iso_dir(self, lba, size, path):
        data = self.read(lba, size); i = 0
        while i < size:
            n = data[i]
            if n == 0: i = (i // SEC + 1) * SEC; continue
            rec = data[i:i + n]; pos = lba * SEC + i; i += n
            loc, ln = struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]
            name = rec[33:33 + rec[32]]
            if name in (b'\0', b'\1'): continue
            p = path + '/' + name.decode('latin1').split(';')[0]
            if rec[25] & 2: self._iso_dir(loc, ln, p)
            else: self.files[p.upper()] = File(p.upper(), loc, ln, pos)

    # --- UDF ---
    def _udf(self):
        avdp = self.read(256)
        assert struct.unpack_from('<H', avdp, 0)[0] == 2, 'no UDF AVDP'
        vds_len, vds_loc = struct.unpack_from('<II', avdp, 16)
        self.part_start = None; fsd = None
        for k in range(vds_len // SEC):
            d = self.read(vds_loc + k); tag = struct.unpack_from('<H', d, 0)[0]
            if tag == 5: self.part_start = struct.unpack_from('<I', d, 188)[0]
            elif tag == 6: fsd = struct.unpack_from('<I', d, 248 + 4)[0]   # long_ad: len, lbn, part
            elif tag == 8: break
        fsdd = self.read(self.part_start + fsd)
        assert struct.unpack_from('<H', fsdd, 0)[0] == 256
        root_lbn = struct.unpack_from('<I', fsdd, 400 + 4)[0]
        self._udf_dir(root_lbn, '')

    def _fe(self, lbn):
        d = self.read(self.part_start + lbn)
        assert struct.unpack_from('<H', d, 0)[0] == 261, 'not a File Entry'
        info_len = struct.unpack_from('<Q', d, 56)[0]
        l_ea, l_ad = struct.unpack_from('<II', d, 168)
        adtype = struct.unpack_from('<H', d, 34)[0] & 7
        assert adtype == 0, 'expected short_ad'
        ads = [struct.unpack_from('<II', d, 176 + l_ea + 8 * k) for k in range(l_ad // 8)]
        return d, info_len, ads, l_ea

    def _udf_dir(self, lbn, path):
        _, ln, ads, _ = self._fe(lbn)
        data = b''.join(self.read(self.part_start + pos, (alen & 0x3FFFFFFF)) for alen, pos in ads)[:ln]
        i = 0
        while i < len(data):
            assert struct.unpack_from('<H', data, i)[0] == 257
            chars = data[i + 18]; l_fi = data[i + 19]
            icb_lbn = struct.unpack_from('<I', data, i + 20 + 4)[0]
            l_iu = struct.unpack_from('<H', data, i + 36)[0]
            name_raw = data[i + 38 + l_iu: i + 38 + l_iu + l_fi]
            i += (38 + l_iu + l_fi + 3) & ~3
            if chars & 8: continue                       # parent
            name = name_raw[1:].decode('latin1') if name_raw[:1] == b'\x08' else name_raw[1:].decode('utf-16-be')
            p = (path + '/' + name).upper()
            if chars & 2: self._udf_dir(icb_lbn, p)
            elif p in self.files: self.files[p].udf_fe = (self.part_start + icb_lbn) * SEC

    def write_udf(self, fobj, lba, size):
        """Point the File Entry at one extent [lba, size)."""
        if fobj.udf_fe is None: return
        self.f.seek(fobj.udf_fe); d = bytearray(self.f.read(SEC))
        l_ea, l_ad = struct.unpack_from('<II', d, 168)
        assert l_ad == 8, f'{fobj.path}: {l_ad // 8} extents, only single-extent files supported'
        struct.pack_into('<Q', d, 56, size)
        struct.pack_into('<Q', d, 64, -(-size // SEC))
        struct.pack_into('<II', d, 176 + l_ea, size, lba - self.part_start)
        crc_len = struct.unpack_from('<H', d, 10)[0]
        struct.pack_into('<H', d, 8, crc_ccitt(d[16:16 + crc_len]))
        d[4] = sum(d[k] for k in range(16) if k != 4) & 0xFF
        self.f.seek(fobj.udf_fe); self.f.write(d)

    def write_iso(self, fobj, lba, size):
        self.f.seek(fobj.iso_rec + 2); self.f.write(both32(lba))
        self.f.seek(fobj.iso_rec + 10); self.f.write(both32(size))


def patch(iso_in, iso_out, repl):
    """repl: {'/MESSAGE/MESARC.AFS': bytes}. Returns {path: (lba, size, moved)}."""
    if os.path.abspath(iso_in) != os.path.abspath(iso_out): shutil.copyfile(iso_in, iso_out)
    log = {}
    with open(iso_out, 'r+b') as f:
        disc = Disc(f); pad = disc.files[PAD]
        for path, data in repl.items():
            fo = disc.files[path.upper()]
            old_secs = -(-fo.size // SEC); new_secs = -(-len(data) // SEC)
            if new_secs <= old_secs:
                lba = fo.lba; moved = False
            else:
                assert new_secs < -(-pad.size // SEC), 'padding exhausted'
                lba = pad.lba; moved = True
                pad.lba += new_secs; pad.size -= new_secs * SEC
                disc.write_iso(pad, pad.lba, pad.size); disc.write_udf(pad, pad.lba, pad.size)
            f.seek(lba * SEC); f.write(data)
            f.write(b'\0' * ((max(new_secs, old_secs if not moved else new_secs) * SEC) - len(data)))
            fo.lba, fo.size = lba, len(data)
            disc.write_iso(fo, lba, len(data)); disc.write_udf(fo, lba, len(data))
            log[path] = (lba, len(data), moved)
    return log


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'list':
        with open(sys.argv[2], 'rb') as f:
            d = Disc(f)
            for p, fo in sorted(d.files.items(), key=lambda x: x[1].lba):
                print(f'{fo.lba:8d} {fo.size:11d} {"U" if fo.udf_fe else "-"} {p}')
    elif cmd == 'put':
        repl = {}
        for a in sys.argv[4:]:
            p, local = a.split('=', 1); repl[p] = open(local, 'rb').read()
        for p, v in patch(sys.argv[2], sys.argv[3], repl).items(): print(p, v)
