#!/usr/bin/env python3
"""Unpack what the build needs from rom/namida.iso into work/ (idempotent).
  work/orig/<ARCHIVE>.AFS, work/orig/SLPM_659.52, work/mes/NNNN_name (MESARC members)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso, afs
from check_rom import check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO = os.path.join(ROOT, 'rom', 'namida.iso')
WORK = os.path.join(ROOT, 'work')
WANT = ['/SLPM_659.52', '/MESSAGE/MESARC.AFS', '/WINDOW/WINARC.AFS', '/DATA/DATAARC.AFS',
        '/EVENT/EVENTARC.AFS', '/SUBGAME/SGARC.AFS', '/BATTLE/BTLARC.AFS', '/EFFECT/EFFARC.AFS']


def unpack(verify=True):
    if verify: check()
    od = os.path.join(WORK, 'orig'); os.makedirs(od, exist_ok=True)
    with open(ISO, 'rb') as f:
        d = iso.Disc(f)
        dlls = [p for p in d.files if p.startswith('/DLL/')]
        for p in WANT + dlls:
            out = os.path.join(od, p[1:] if p.startswith('/DLL/') else os.path.basename(p))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            fo = d.files[p]
            if os.path.isfile(out) and os.path.getsize(out) == fo.size: continue
            f.seek(fo.lba * iso.SEC); open(out, 'wb').write(f.read(fo.size))
    md = os.path.join(WORK, 'mes')
    a = afs.Afs(os.path.join(od, 'MESARC.AFS'))
    if not os.path.isdir(md) or len(os.listdir(md)) != len(a.ents):
        os.makedirs(md, exist_ok=True)
        for i, name, _, _ in a.ents:
            open(os.path.join(md, f'{i:04d}_{name}'), 'wb').write(a.data(i))
    return od, md


if __name__ == '__main__':
    print(unpack())
