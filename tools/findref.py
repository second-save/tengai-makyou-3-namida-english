#!/usr/bin/env python3
"""Find lui/off pairs (within 8 insns) that address TARGET in SLPM. usage: findref.py 0xADDR"""
import struct, sys
t = int(sys.argv[1], 0); hi = (t + 0x8000) >> 16; lo = t - (hi << 16)
d = open(sys.argv[2] if len(sys.argv) > 2 else 'orig/SLPM_659.52', 'rb').read(); base = 0xFF000
names = {0x23:'lw',0x2b:'sw',0x09:'addiu',0x21:'lh',0x25:'lhu',0x20:'lb',0x24:'lbu',0x28:'sb',0x29:'sh',0x37:'ld',0x3f:'sd'}
for o in range(0x1000, 0x5e0000, 4):
    w, = struct.unpack_from('<I', d, o)
    if w >> 26 == 0xF and (w & 0xFFFF) == hi:
        r = (w >> 16) & 31
        for k in range(1, 9):
            w2, = struct.unpack_from('<I', d, o + 4 * k); op = w2 >> 26
            imm = w2 & 0xFFFF; imm = imm - 0x10000 if imm & 0x8000 else imm
            if op in names and (w2 >> 21) & 31 == r and imm == lo:
                print(hex(o + base + 4 * k), names[op]); break
