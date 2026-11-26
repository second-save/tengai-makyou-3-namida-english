#!/usr/bin/env python3
"""Region list for the warp tool, from a memory dump of a running game (tools/memdump.py):

  memdump.py ISO SLOT work/dump/slot1 0x1ed36f8:0x8000 0x1edb824:0x5400
  (region table = *0x7c79dc, 8 B each: a, b, area s16, angle; area table = *0x7c79d8, 0x1c B each, +0 = name
   index into mapldmes; PartyMapRegionAreaNameGet @ 0x146660. The pointers held these values in slot 1.)

usage: regions.py DUMPDIR > tools/debug/regions.tsv
"""
import json, os, re, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NREG = 0xA00      # region ids in use stay below this (0x9cb = Dejima is the highest referenced in code)


def main(d):
    A = open(os.path.join(d, '1ed36f8.bin'), 'rb').read()
    R = open(os.path.join(d, '1edb824.bin'), 'rb').read()
    mp = json.load(open(os.path.join(ROOT, 'script', 'mapldmes.json'), encoding='utf-8'))['strings']
    clean = lambda s: re.sub(r'\{ruby:([^|]*)\|[^}]*\}', r'\1', s)
    print('region\tarea\tname_idx\tname')
    for r in range(min(NREG, len(R) // 8)):
        area = struct.unpack_from('<h', R, r * 8 + 4)[0]
        if area < 0 or area * 0x1C + 2 > len(A): continue
        ni = struct.unpack_from('<h', A, area * 0x1C)[0]
        name = clean(mp[ni]['jp']) if 0 <= ni < len(mp) else ''
        print(f'{r:#05x}\t{area}\t{ni}\t{name}')


if __name__ == '__main__':
    main(sys.argv[1])
