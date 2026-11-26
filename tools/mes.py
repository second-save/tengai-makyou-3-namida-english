#!/usr/bin/env python3
"""Decode Namida message files (MESARC *mes.cmp + *.ofs) to text.

Container (after CMP decompression), see ws_mess_data_create @ 0x410d58:
  +0  'MD'
  +2  BE u16 base   first non-glyph code (0xA72 = number of font glyphs)
  +4  BE u16 ncmd   number of 4-byte command records
  +6  BE u16 ndict  number of dictionary strings
  +8  (2 bytes, unused here)
  +10 ncmd * 4 bytes command records: [type, a, b, c]
      then ndict strings of 12-bit codes, each ending with 0xFFF, byte-aligned
  strings referenced by .ofs (LE u32 offsets) are 12-bit code streams ending 0xFFF
Codes: < base glyph (font.cmp gives SJIS), 0xFFE newline, 0xFFF end,
       base..base+ncmd-1 command, base+ncmd.. dictionary entry.
"""
import struct, sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from cmp import decompress

def read12(d, i):
    """yield (code, next_index) for a 12-bit big-nibble stream starting at byte i"""
    half = False
    while True:
        if not half:
            c = (d[i] << 4) | (d[i + 1] >> 4); i += 1; half = True
        else:
            c = ((d[i] & 15) << 8) | d[i + 1]; i += 2; half = False
        yield c, (i + 1 if half else i)
        if c == 0xFFF: return

def codes_at(d, i):
    out = []
    for c, nxt in read12(d, i):
        if c == 0xFFF: return out, nxt
        out.append(c)

def load_font_table(path):
    t = decompress(open(path, 'rb').read())
    tab = []
    for k in range(0, len(t), 2):
        a, b = t[k], t[k + 1]
        tab.append(chr(b) if a == 0 else bytes([a, b]).decode('cp932', 'replace'))
    return tab

class MesFile:
    def __init__(self, cmp_path, ofs_path, font):
        self.d = d = decompress(open(cmp_path, 'rb').read())
        assert d[:2] == b'MD', cmp_path
        self.base, self.ncmd, self.ndict = struct.unpack_from('>HHH', d, 2)
        self.cmds = [tuple(d[10 + 4 * k:14 + 4 * k]) for k in range(self.ncmd)]
        i = 10 + 4 * self.ncmd; self.dict = []
        for _ in range(self.ndict):
            cs, i = codes_at(d, i); self.dict.append(cs)
        o = open(ofs_path, 'rb').read()
        self.offsets = list(struct.unpack(f'<{len(o)//4}I', o))
        self.font = font

    def render(self, codes, depth=0):
        s = []
        for c in codes:
            if c < self.base: s.append(self.font[c])
            elif c == 0xFFE: s.append('\n')
            elif c < self.base + self.ncmd:
                t = self.cmds[c - self.base]
                s.append('{' + ' '.join(f'{x:02x}' for x in t) + '}')
            else:
                k = c - self.base - self.ncmd
                s.append(self.render(self.dict[k], depth + 1) if k < len(self.dict) else f'{{?{c:03x}}}')
        return ''.join(s)

    def messages(self):
        for n, off in enumerate(self.offsets):
            cs, _ = codes_at(self.d, off)
            yield n, off, self.render(cs)

if __name__ == '__main__':
    mesdir = sys.argv[1]; files = sorted(os.listdir(mesdir))
    font = load_font_table(os.path.join(mesdir, [f for f in files if f.endswith('_font.cmp')][0]))
    targets = sys.argv[2:] or [f[5:-4] for f in files if f.endswith('mes.cmp')]
    for name in targets:
        cmp_ = [f for f in files if f[5:] == name + '.cmp'][0]
        ofs = [f for f in files if f[5:] == name + '.ofs'][0]
        m = MesFile(os.path.join(mesdir, cmp_), os.path.join(mesdir, ofs), font)
        print(f'### {name}  base={m.base:#x} cmds={m.cmds} dict={len(m.dict)}')
        for n, off, txt in m.messages():
            print(f'[{n}] ' + txt.replace('\n', '\n    '))
