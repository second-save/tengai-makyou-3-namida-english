#!/usr/bin/env python3
"""Namida dialogue font (MESARC #3-6 font_0000..0003.tex), per FNTSetRasterUv @ 0x3b9778:
  glyph g: texture g // 722, plane g & 1, cell (g % 722) // 2, row cell // 19, col cell % 19,
  25x25 px at (col*26, row*26). Texture = 0x120-byte header + 512x512 4bpp (low nibble = left
  pixel; the file stops 208 bytes short of the full 512x512, the missing tail is empty).
  Each pixel's 4 bits hold two 2bpp planes: odd glyphs in bits 0-1, even glyphs in bits 2-3.

usage: font.py sheet MESDIR OUT.png [tex]   (render glyph sheet with codes, for checking)
"""
import os, sys
import numpy as np

CELL, PITCH, COLS, PER_TEX, HDR = 25, 26, 19, 722, 0x120


def load_tex(path):
    """-> (file bytes, 512x512 uint8 array of 4-bit values)"""
    return load_tex_bytes(open(path, 'rb').read())


def load_tex_bytes(d):
    raw = np.frombuffer((d[HDR:] + bytes(512 * 256))[:512 * 256], np.uint8)
    px = np.empty(raw.size * 2, np.uint8); px[0::2] = raw & 15; px[1::2] = raw >> 4
    return d, px.reshape(512, 512).copy()


def save_tex(orig, img4):
    """Write img4 back into a copy of the original file (same length)."""
    flat = img4.reshape(-1).astype(np.uint8)
    data = bytes((flat[0::2] & 15) | ((flat[1::2] & 15) << 4))
    n = len(orig) - HDR
    assert not any(data[n:]), 'pixels beyond the end of the texture file'
    return orig[:HDR] + data[:n]


def glyph_rect(g):
    r = g % PER_TEX; cell = r // 2
    return g // PER_TEX, g & 1, (cell % COLS) * PITCH, (cell // COLS) * PITCH


def plane_shift(plane, swap=False):
    return (0 if plane else 2) ^ (2 if swap else 0)


def get_glyph(texs, g, swap=False):
    t, p, x, y = glyph_rect(g)
    return (texs[t][y:y + CELL, x:x + CELL] >> plane_shift(p, swap)) & 3


def put_glyph(texs, g, a2, swap=False):
    t, p, x, y = glyph_rect(g); sh = plane_shift(p, swap)
    cell = texs[t][y:y + CELL, x:x + CELL]
    cell &= ~np.uint8(3 << sh) & 0xF
    cell |= (a2.astype(np.uint8) & 3) << sh
    # The game samples the gap row above each cell too (original ^ | ~ ink there); clear it, or the old
    # glyph's top shows as a stray bar above the new one (seen in the torture line, 2026-11-19).
    if y > 0:
        texs[t][y - 1, x:x + CELL] &= ~np.uint8(3 << sh) & 0xF


def tex_paths(mesdir):
    fs = sorted(os.listdir(mesdir))
    return [os.path.join(mesdir, [f for f in fs if f.endswith(f'_font_000{k}.tex')][0]) for k in range(4)]


if __name__ == '__main__' and sys.argv[1] == 'sheet':
    from PIL import Image, ImageDraw
    mesdir, out = sys.argv[2], sys.argv[3]
    swap = '--swap' in sys.argv
    texs = [load_tex(p)[1] for p in tex_paths(mesdir)]
    first = int(sys.argv[4], 0) if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else 0
    n = 200; cols = 20; z = 2
    img = Image.new('L', (cols * 40 * z, (n // cols) * 46 * z)); dr = ImageDraw.Draw(img)
    for k in range(n):
        g = first + k
        a = get_glyph(texs, g, swap) * 85
        im = Image.fromarray(a.astype(np.uint8)).resize((CELL * z, CELL * z), Image.NEAREST)
        x, y = (k % cols) * 40 * z, (k // cols) * 46 * z
        img.paste(im, (x, y + 10 * z)); dr.text((x, y), f'{g:03x}', fill=255)
    img.save(out)
