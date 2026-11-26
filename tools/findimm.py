#!/usr/bin/env python3
"""Find instructions loading an immediate (addiu/ori rX, zero, IMM) in SLPM_659.52; prints address + function.
usage: findimm.py IMM [IMM..]    e.g. MESARC member indices"""
import bisect, os, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = open(os.path.join(ROOT, 'work', 'orig', 'SLPM_659.52'), 'rb').read(); BASE = 0xFF000
syms = sorted((int(a, 16), n) for n, a in (l.split() for l in open(os.path.join(ROOT, 'work', 'symbols.txt'))))
addrs = [a for a, _ in syms]
want = {int(x, 0) for x in sys.argv[1:]}
for o in range(0x1000, 0x1000 + 0x5E0000, 4):
    w, = struct.unpack_from('<I', d, o); op = w >> 26
    if op in (0x09, 0x0D) and (w >> 21) & 31 == 0 and (w & 0xFFFF) in want:
        va = o + BASE; k = bisect.bisect_right(addrs, va) - 1
        print(f'{va:#x} imm {w & 0xFFFF:#x} in {syms[k][1]}+{va - syms[k][0]:#x}')
