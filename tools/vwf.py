#!/usr/bin/env python3
"""Variable-width English font (decisions.md D8).

The game's font already has printable ASCII at glyph codes 0x00-0x5E (font.cmp order: space..'_', 'a'..'~',
no backtick) and a per-glyph advance table at 0x783210 (u8, advance - 1, all 12 originally) that
ws_printf2 uses for codes < 0x60. We redraw those glyphs in PT Serif, one character per glyph, left-aligned
in its 25x25 cell, and write real advances into the table. tools/elfpatch.py makes the message window,
its line-width routine and the speaker nameplate advance by the same table.

usage: vwf.py preview "text" OUT.png [--scale N]
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTF = os.path.join(ROOT, 'fonts', 'PT_Serif-Web-Regular.ttf')
SIZE = 19          # px em; tested readable at native resolution (pair font, 2026-11-19)
BASELINE = 18      # y of the baseline inside the 25 px cell
LEFT = 1           # pen x inside the cell (the outline is drawn as 8 offset copies)
CELL = 25
SS = 4             # supersampling
NCODES = 0x5F      # ASCII glyph codes 0x00..0x5E
TABLE_VA = 0x783210
TRACK = 1          # px added to every advance (the outline needs room between letters)


class VwfFont:
    def __init__(self, ttf=TTF, size=SIZE, baseline=BASELINE):
        self.f = ImageFont.truetype(ttf, size * SS)
        self.size, self.baseline = size, baseline

    def advance(self, ch):
        a = self.__dict__.setdefault('_adv', {}).get(ch)    # getlength is slow; the lint measures millions of glyphs
        if a is None:
            a = self._adv[ch] = (max(4, int(round(self.f.getlength(' ') / SS))) if ch == ' '
                                 else max(2, int(round(self.f.getlength(ch) / SS)) + TRACK))
        return a

    def render(self, ch):
        """-> 25x25 uint8 in 0..3"""
        asc = self.f.getmetrics()[0]
        big = Image.new('L', (CELL * SS, CELL * SS), 0)
        if ch != ' ':
            ImageDraw.Draw(big).text((LEFT * SS, self.baseline * SS - asc), ch, font=self.f, fill=255)
        a = np.asarray(big.resize((CELL, CELL), Image.LANCZOS), np.float32) / 255.0
        return np.clip(np.round(a * 3), 0, 3).astype(np.uint8)


def glyph_set(font_chars):
    """font_chars: the game's code -> char list. Returns [(code, char)] for the ASCII range."""
    return [(g, font_chars[g]) for g in range(NCODES)]


def width_table(vf, font_chars):
    """bytes for TABLE_VA: advance - 1 per code 0..0x5F (0x5F, not redrawn, keeps 12)."""
    t = bytearray([12] * 0x60)
    for g, ch in glyph_set(font_chars):
        t[g] = vf.advance(ch) - 1
    return bytes(t)


def text_width(vf, s):
    return sum(vf.advance(c) for c in s)


def preview(text, out, scale=3):
    vf = VwfFont()
    lines = text.split('\\n')
    w = max(text_width(vf, l) for l in lines) + CELL
    img = np.zeros((CELL * len(lines) + 4, w), np.uint8)
    for li, line in enumerate(lines):
        x = 0
        for ch in line:
            g = vf.render(ch); y = li * CELL
            img[y:y + CELL, x:x + CELL] = np.maximum(img[y:y + CELL, x:x + CELL], g[:, :min(CELL, w - x)])
            x += vf.advance(ch)
    pal = np.array([[30, 20, 10], [110, 90, 70], [190, 175, 150], [255, 250, 235]], np.uint8)
    Image.fromarray(pal[img]).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(out)


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'preview':
        sc = int(sys.argv[sys.argv.index('--scale') + 1]) if '--scale' in sys.argv else 3
        preview(sys.argv[2], sys.argv[3], sc)
    else:
        print(__doc__)
