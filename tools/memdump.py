#!/usr/bin/env python3
"""Boot an ISO in the repo's PCSX2, load a savestate slot, dump EE memory ranges, quit.

usage: memdump.py ISO SLOT OUTDIR ADDR:LEN [ADDR:LEN ...] [--ptr ADDR:LEN]
  ADDR:LEN   dump LEN bytes at ADDR to OUTDIR/<addr>.bin
  --ptr P:L  read the u32 at P and dump L bytes at that address (OUTDIR/ptr_<P>.bin, prints the pointer)
The savestate must come from the same build (a different ELF breaks on load).
"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcsx2 import Emu


def read_big(pine, a, n):
    out = bytearray()
    for o in range(0, n, 4):
        out += struct.pack('<I', pine.read32(a + o))
    return bytes(out[:n])


def main():
    args = sys.argv[1:]
    iso, slot, outdir = args[0], int(args[1]), args[2]
    os.makedirs(outdir, exist_ok=True)
    emu = Emu(iso).start()
    try:
        emu.pine.load(slot); time.sleep(4)
        i = 3
        while i < len(args):
            if args[i] == '--ptr':
                p, n = (int(x, 0) for x in args[i + 1].split(':')); i += 2
                a = emu.pine.read32(p); print(f'ptr {p:#x} -> {a:#x}')
                open(os.path.join(outdir, f'ptr_{p:x}.bin'), 'wb').write(read_big(emu.pine, a, n))
            else:
                a, n = (int(x, 0) for x in args[i].split(':')); i += 1
                open(os.path.join(outdir, f'{a:x}.bin'), 'wb').write(read_big(emu.pine, a, n))
                print(f'{a:#x}: {n} bytes')
    finally:
        emu.stop()


if __name__ == '__main__':
    main()
