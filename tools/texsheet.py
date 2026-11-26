#!/usr/bin/env python3
"""Labelled contact sheets of texture PNGs of mixed sizes (for the graphics-text survey).
usage: texsheet.py OUTPREFIX PNG.. [--max-w 1600] [--per 60] [--scale-max 256]
Writes OUTPREFIX_01.png ... ; each tile is scaled to fit scale-max px and labelled with its file name."""
import os, sys
from PIL import Image, ImageDraw


def main():
    a = sys.argv[1:]
    def opt(k, d):
        if k in a: i = a.index(k); v = a[i + 1]; del a[i:i + 2]; return int(v)
        return d
    maxw, per, smax = opt('--max-w', 1600), opt('--per', 60), opt('--scale-max', 256)
    prefix, files = a[0], a[1:]
    for page in range(0, len(files), per):
        tiles = []
        for f in files[page:page + per]:
            im = Image.open(f).convert('RGBA')
            s = min(1.0, smax / max(im.size))
            if im.width * s < 48 and im.height * s < 48: s = min(4.0, 48 / max(im.size))
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.NEAREST)
            bg = Image.new('RGBA', im.size, (60, 60, 70, 255)); bg.alpha_composite(im)
            tiles.append((os.path.basename(f)[:40], bg))
        rows, x, y, rh = [], 0, 0, 0
        pos = []
        for name, im in tiles:
            w, h = max(im.width, 150), im.height + 12
            if x + w > maxw: x = 0; y += rh + 6; rh = 0
            pos.append((x, y)); x += w + 6; rh = max(rh, h)
        sheet = Image.new('RGB', (maxw, y + rh + 6), (20, 20, 20)); dr = ImageDraw.Draw(sheet)
        for (name, im), (px, py) in zip(tiles, pos):
            dr.text((px, py), name, fill=(255, 255, 0)); sheet.paste(im.convert('RGB'), (px, py + 12))
        out = f'{prefix}_{page // per + 1:02d}.png'; sheet.save(out); print(out)


if __name__ == '__main__':
    main()
