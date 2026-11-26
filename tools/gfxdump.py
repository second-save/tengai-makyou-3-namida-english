#!/usr/bin/env python3
"""Dump every decodable texture of an AFS archive to PNG (graphics-text survey).

usage: gfxdump.py ARCHIVE [--out work/gfx] [--skip REGEX] [--iso ISO]   (--iso: read ARCHIVE from that disc, e.g. a build)
  -> work/gfx/ARCHIVE/<member>__<texname>.png, and a list of undecoded textures on stdout
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs, txd, unpack
from PIL import Image


def main(argv):
    arc = argv[0]
    out = argv[argv.index('--out') + 1] if '--out' in argv else 'work/gfx'
    skip = re.compile(argv[argv.index('--skip') + 1]) if '--skip' in argv else None
    if '--iso' in argv:                              # dump from a built disc (leftover scan): copy the archive out first
        import iso, tempfile
        with open(argv[argv.index('--iso') + 1], 'rb') as f:
            disc = iso.Disc(f); p = next(k for k in disc.files if k.upper().endswith('/' + arc.upper()))
            fo = disc.files[p]; f.seek(fo.lba * iso.SEC)
            tmp = os.path.join(tempfile.mkdtemp(), arc)
            with open(tmp, 'wb') as g:
                left = fo.size
                while left: chunk = f.read(min(left, 1 << 24)); g.write(chunk); left -= len(chunk)
        a = afs.Afs(tmp)
    else:
        od, _ = unpack.unpack()
        a = afs.Afs(os.path.join(od, arc))
    d = os.path.join(out, arc.split('.')[0]); os.makedirs(d, exist_ok=True)
    n = bad = 0
    for i, e in enumerate(a.ents):
        m = e[1]
        if skip and skip.search(m): continue
        try: texs = txd.textures(a.data(i))
        except Exception: continue
        for t in texs:
            if t.get('img') is None:
                bad += 1; print('undecoded', m, t.get('name'), t.get('why')); continue
            Image.fromarray(t['img'], 'RGBA').save(os.path.join(d, f'{m.split(".")[0]}__{t["name"]}.png')); n += 1
    print(f'{arc}: {n} textures written to {d}, {bad} undecoded')


if __name__ == '__main__':
    main(sys.argv[1:])
