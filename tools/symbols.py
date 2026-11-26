#!/usr/bin/env python3
"""Recover function names from SLPM_659.52's own (name ptr, function ptr) export tables.
usage: symbols.py ELF OUT.txt     -> lines "name 0xaddr" sorted by address (for ApplySyms.java)"""
import re, struct, sys

BASE = 0xFF000                      # file offset = VA - BASE
TEXT_END, DATA_END = 0x5E0000, 0x100000 + 0x691E04


def scan(d):
    def cstr(va):
        o = va - BASE
        if not 0 <= o < len(d): return None
        e = d.find(b'\0', o, o + 80)
        if e < 0: return None
        s = d[o:e]
        return s.decode() if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_]{2,}', s) else None
    syms = {}
    for o in range(0, len(d) - 8, 4):
        n, f = struct.unpack_from('<II', d, o)
        if 0x100000 <= f < TEXT_END and f % 4 == 0 and TEXT_END <= n < DATA_END:
            s = cstr(n)
            if s: syms.setdefault(s, f)
    return syms


if __name__ == '__main__':
    syms = scan(open(sys.argv[1], 'rb').read())
    with open(sys.argv[2], 'w') as g:
        for s, f in sorted(syms.items(), key=lambda x: x[1]): g.write(f'{s} {f:#x}\n')
    print(len(syms), 'symbols')
