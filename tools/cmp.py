#!/usr/bin/env python3
"""Namida 'CMP\\0' container (CmpDecompress @ 0x11ac28 in SLPM_659.52).
header: 'CMP\\0', u32 LE raw size.  Bitstream MSB-first; flag bytes are fetched lazily,
interleaved with data bytes in the order the decoder asks for them:
  1           literal byte
  0 0 LL      LL!=0: copy LL+1 bytes (2..4) from dist = 256-b  (1 byte b; dist 1..256)
              LL==0: u16 LE w: len = (w&15)+1 (1..16), dist = 0x1000-(w>>4) (1..4096)
  0 1         byte n: n==0 -> end; else copy n+1 bytes (2..256) from dist 1 (run of last byte)

usage: cmp.py d IN OUT | cmp.py c IN OUT
"""
import struct, sys


class Bits:
    def __init__(s, b, i): s.b, s.i, s.cnt, s.buf = b, i, 0, 0

    def byte(s):
        v = s.b[s.i]; s.i += 1; return v

    def bit(s):
        if s.cnt == 0: s.buf = s.byte(); s.cnt = 8
        s.cnt -= 1; return (s.buf >> s.cnt) & 1

    def bits2(s):
        if s.cnt < 2: s.buf = ((s.buf << 8) | s.byte()) & 0xFFFF; s.cnt += 8
        s.cnt -= 2; return (s.buf >> s.cnt) & 3


def decompress(buf):
    assert buf[:3] == b'CMP'
    size = struct.unpack_from('<I', buf, 4)[0]
    r = Bits(buf, 8); out = bytearray()
    while True:
        if r.bit():
            out.append(r.byte()); continue
        if r.bit() == 0:
            ll = r.bits2()
            if ll == 0:
                w = r.byte() | (r.byte() << 8)
                n = (w & 15) + 1; dist = 0x1000 - (w >> 4)
            else:
                n = ll + 1; dist = 0x100 - r.byte()
            for _ in range(n): out.append(out[-dist])
        else:
            n = r.byte()
            if n == 0: break
            for _ in range(n + 1): out.append(out[-1])
    assert len(out) == size, (len(out), size)
    return bytes(out)


class BitWriter:
    """Mirror of Bits: a flag byte is reserved in the output when its first bit is written."""
    def __init__(s): s.out = bytearray(b'CMP\0\0\0\0\0'); s.pos = -1; s.cnt = 0

    def bit(s, v):
        if s.cnt == 0: s.pos = len(s.out); s.out.append(0); s.cnt = 8
        s.cnt -= 1
        if v: s.out[s.pos] |= 1 << s.cnt

    def byte(s, v): s.out.append(v)


def compress(data, window=4096, max_chain=64):
    data = bytes(data); n = len(data)
    w = BitWriter(); heads = {}; i = 0

    def insert(p):
        if p + 2 < n:
            heads.setdefault(data[p:p + 3], []).append(p)

    def best_match(p):
        best_len, best_dist = 0, 0
        # run of the previous byte (RLE token, dist 1, up to 256)
        cand = heads.get(data[p:p + 3], ())
        limit = min(256, n - p)
        for q in reversed(cand[-max_chain:]):
            d = p - q
            if d > window: break
            m = 0
            mx = min(limit, 16 if d > 1 else 256)
            while m < mx and data[q + m] == data[p + m]: m += 1
            if m > best_len: best_len, best_dist = m, d
            if m == mx: break
        if best_len < 3 and p >= 1 and p + 1 < n:   # 2-byte short matches within 256
            for d in range(1, min(256, p) + 1):
                if data[p - d] == data[p] and data[p - d + 1] == data[p + 1]:
                    return 2, d
        return best_len, best_dist

    while i < n:
        ln, d = best_match(i) if i + 1 < n else (0, 0)
        if d == 1 and ln > 16:
            ln = min(ln, 256)
            w.bit(0); w.bit(1); w.byte(ln - 1)
        elif ln >= 2 and d <= 256 and ln <= 4:
            w.bit(0); w.bit(0); ll = ln - 1; w.bit(ll >> 1); w.bit(ll & 1); w.byte((0x100 - d) & 0xFF)
        elif ln >= 3:
            ln = min(ln, 16)
            if d <= 256 and ln <= 4:
                w.bit(0); w.bit(0); ll = ln - 1; w.bit(ll >> 1); w.bit(ll & 1); w.byte((0x100 - d) & 0xFF)
            else:
                v = ((0x1000 - d) << 4) | (ln - 1)
                w.bit(0); w.bit(0); w.bit(0); w.bit(0); w.byte(v & 0xFF); w.byte(v >> 8)
        else:
            ln = 1
            w.bit(1); w.byte(data[i])
        for k in range(ln): insert(i + k)
        i += ln
    w.bit(0); w.bit(1); w.byte(0)
    struct.pack_into('<I', w.out, 4, n)
    return bytes(w.out)


if __name__ == '__main__':
    mode, src, dst = sys.argv[1:4]
    b = open(src, 'rb').read()
    open(dst, 'wb').write(decompress(b) if mode == 'd' else compress(b))
