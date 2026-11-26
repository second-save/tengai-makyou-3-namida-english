#!/usr/bin/env python3
"""Find MIPS loads/stores (or any I-type op) with a given 16-bit immediate in the ELF and every DLL.

usage: findimm.py IMM [IMM...] [--all-ops]     e.g. findimm.py 0x3d1 0x3d3
Default: only load/store opcodes (lb..sd, lwc1/swc1, lq/sq). Prints file, VA (ELF) or file offset, word.
"""
import glob, os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LS = set(range(0x20, 0x40)) | {0x1A, 0x1B, 0x1E, 0x1F}
BASE = 0xFF000


def scan(imms, all_ops=False):
    files = [os.path.join(ROOT, 'work/orig/SLPM_659.52')] + sorted(
        glob.glob(os.path.join(ROOT, 'work/orig/DLL/**/*.*'), recursive=True))
    for f in files:
        b = open(f, 'rb').read()
        n = len(b) // 4
        for i, w in enumerate(struct.unpack('<%dI' % n, b[:4 * n])):
            if (w & 0xFFFF) in imms and (all_ops or (w >> 26) in LS):
                rel = os.path.relpath(f, ROOT)
                where = f'{i * 4 + BASE:#x}' if rel.endswith('SLPM_659.52') else f'+{i * 4:#x}'
                yield rel, where, w


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for rel, where, w in scan({int(a, 0) for a in args}, '--all-ops' in sys.argv):
        print(rel, where, f'{w:08x}')
