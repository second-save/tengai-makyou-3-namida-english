#!/usr/bin/env python3
"""Message script <-> MESARC message files.

Text syntax (one string = codes up to 0xFFF, dictionary references expanded inline):
  newline              real "\\n"
  {name}               record 11 00 00 00  (speaker name delimiter, used in pairs)
  {ruby:漢字|かんじ}     record 07 a b 00 + a base glyphs + b reading glyphs
  {choice} {branch}    records 0e / 0f   (choice list start / branch separator)
  {var} {num}          records 04 / 05   (string variable: item, enemy; number variable)
  {btn:XX}             record 0c XX 00 00 (button icon)
  {XX YY ZZ WW}        any other record, trailing 00 bytes dropped  e.g. {0d 00 07 2a}
  {lb} {rb}            literal { } glyphs;  {g:XXX} glyph by code

usage: script.py extract MESDIR OUTDIR     (MESDIR = MESARC members extracted by afs.py)
"""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mes import codes_at, load_font_table
from cmp import decompress, compress

ALIASES = {0x11: 'name', 0x0E: 'choice', 0x0F: 'branch', 0x04: 'var', 0x05: 'num'}
ALIAS_REV = {v: k for k, v in ALIASES.items()}
NL, END = 0xFFE, 0xFFF


class MdFile:
    """A decompressed 'MD' message file: commands, dictionary, strings (codes, dict expanded)."""
    def __init__(self, raw, offsets):
        assert raw[:2] == b'MD'
        self.raw, self.offsets = bytes(raw), list(offsets)
        self.base, ncmd, ndict = struct.unpack_from('>HHH', raw, 2)
        self.cmds = [bytes(raw[10 + 4 * k:14 + 4 * k]) for k in range(ncmd)]
        i = 10 + 4 * ncmd; self.dict = []
        for _ in range(ndict):
            cs, i = codes_at(raw, i); self.dict.append(cs)
        self.strings = []; self.raw_strings = []
        for o in offsets:
            cs, _ = codes_at(raw, o); ex = []
            for c in cs:
                if self.base + ncmd <= c < NL: ex += self.dict[c - self.base - ncmd]
                else: ex.append(c)
            self.strings.append(ex); self.raw_strings.append(cs)

    def raw_for(self, k, ncmd_new):
        """String k with its dictionary references kept, renumbered for a command table of ncmd_new."""
        d = len(self.cmds); shift = ncmd_new - d
        return [c + shift if self.base + d <= c < NL else c for c in self.raw_strings[k]]


def codes_to_text(codes, base, cmds, font):
    out = []; k = 0
    while k < len(codes):
        c = codes[k]; k += 1
        if c == NL: out.append('\n')
        elif c < base:
            ch = font[c] if c < len(font) else None
            out.append('{lb}' if ch == '{' else '{rb}' if ch == '}' else ch if ch else f'{{g:{c:03x}}}')
        else:
            r = cmds[c - base]; t = r[0]
            if t == 7 and r[3] == 0 and k + r[1] + r[2] <= len(codes) and all(x < base for x in codes[k:k + r[1] + r[2]]):
                seg = codes[k:k + r[1] + r[2]]; k += r[1] + r[2]
                out.append('{ruby:' + ''.join(font[x] for x in seg[:r[1]]) + '|' + ''.join(font[x] for x in seg[r[1]:]) + '}')
            elif t in ALIASES and r[1:] == b'\0\0\0': out.append('{' + ALIASES[t] + '}')
            elif t == 0x0C and r[2:] == b'\0\0': out.append(f'{{btn:{r[1]:02x}}}')
            else:
                b = bytes(r).rstrip(b'\0') or b'\0'
                out.append('{' + ' '.join(f'{x:02x}' for x in b) + '}')
    return ''.join(out)


TAG = re.compile(r'\{([^{}]*)\}')


class Encoder:
    """font: code -> char list. English maps to the ASCII glyphs 0x00-0x5E (VWF, see vwf.py)."""
    def __init__(self, font, extra=None):
        self.cmap = {ch: i for i, ch in enumerate(font)}
        if extra: self.cmap.update(extra)

    def glyphs(self, s, where):
        out = []
        for ch in s:
            if ch not in self.cmap: raise ValueError(f'{where}: no glyph for {ch!r}')
            out.append(self.cmap[ch])
        return out

    def encode(self, text, base, cmds, where=''):
        """-> codes; appends any new record to cmds (list of 4-byte bytes)."""
        def rec(b):
            b = bytes(b).ljust(4, b'\0')
            if b not in cmds: cmds.append(b)
            return base + cmds.index(b)
        out = []; pos = 0
        for m in TAG.finditer(text):
            out += self._plain(text[pos:m.start()], where); pos = m.end()
            t = m.group(1)
            if t == 'lb': out.append(self.cmap['{'])
            elif t == 'rb': out.append(self.cmap['}'])
            elif t.startswith('g:'): out.append(int(t[2:], 16))
            elif t.startswith('ruby:'):
                a, b = t[5:].split('|'); ga, gb = self.glyphs(a, where), self.glyphs(b, where)
                out += [rec([7, len(ga), len(gb)])] + ga + gb
            elif t in ALIAS_REV: out.append(rec([ALIAS_REV[t]]))
            elif t.startswith('btn:'): out.append(rec([0x0C, int(t[4:], 16)]))
            elif re.fullmatch(r'[0-9a-f]{2}( [0-9a-f]{2}){0,3}', t): out.append(rec(bytes.fromhex(t)))
            else: raise ValueError(f'{where}: unknown tag {{{t}}}')
        out += self._plain(text[pos:], where)
        return out

    def _plain(self, s, where):
        out = []
        for line_no, part in enumerate(s.split('\n')):
            if line_no: out.append(NL)
            out += self.glyphs(part, where)
        return out


def pack12(codes):
    """codes ending with END -> bytes, byte-aligned (low nibble 0 when odd)."""
    out = bytearray(); half = None
    for c in codes:
        if half is None:
            out.append(c >> 4); half = c & 15
        else:
            out.append(((half << 4) | (c >> 8)) & 0xFF); out.append(c & 0xFF); half = None
    if half is not None: out.append(half << 4)
    return bytes(out)


def build_md(base, cmds, strings, dictionary=(), pins=None):
    """strings: list of code lists (no END), may reference dictionary entries (base+len(cmds)+k).
    pins: {string index: offset} strings that must sit at a given offset (the others are packed around them;
    gaps are never read: strings are found by offset). A pinned string becomes a 3-byte [dict ref, END] stub to
    a dictionary entry holding its text, so it fits whatever room its old slot had. -> (md bytes, offsets).
    Header bytes 8-9 = offset of the first string (after the dictionary)."""
    pins = pins or {}
    if pins:
        dictionary, strings = list(dictionary), list(strings)
        for k in sorted(pins):
            dictionary.append(strings[k]); strings[k] = [base + len(cmds) + len(dictionary) - 1]
        if base + len(cmds) + len(dictionary) > 0xFFE: raise LayoutError('no dictionary codes left for pins')
    dict_bytes = b''.join(pack12(list(d) + [END]) for d in dictionary)
    body_start = 10 + 4 * len(cmds) + len(dict_bytes)
    assert body_start <= 0xFFFF
    head = bytearray(b'MD') + struct.pack('>HHHH', base, len(cmds), len(dictionary), body_start)
    head += b''.join(cmds) + dict_bytes
    packed = [pack12(list(cs) + [END]) for cs in strings]
    taken = sorted((p, p + len(packed[k])) for k, p in pins.items())
    assert all(a >= body_start for a, _ in taken) and all(b <= c for (_, b), (c, _) in zip(taken, taken[1:])), 'pins overlap'
    out = bytearray(head); offs = [None] * len(strings)
    for k, b in enumerate(packed):
        if k in pins: continue
        pos = len(out)
        for a, e in taken:
            if pos < e and a < pos + len(b): pos = e       # skip over a pinned string (ranges sorted)
        out += b'\0' * (pos - len(out)); offs[k] = pos; out += b
    for k, p in pins.items():
        if len(out) < p + len(packed[k]): out += b'\0' * (p + len(packed[k]) - len(out))
        out[p:p + len(packed[k])] = packed[k]; offs[k] = p
    return bytes(out), offs


class LayoutError(Exception):
    pass


def _filler(r):
    """One entry of exactly r bytes (r % 3 != 1): r//... codes 0 (space glyph) + END."""
    n1 = 2 * r // 3 if r % 3 == 0 else (2 * r - 1) // 3        # codes incl. END
    b = pack12([0] * (n1 - 1) + [END]); assert len(b) == r, (r, len(b))
    return b


def _fillers(r):
    """At most two dictionary entries totalling exactly r bytes (r == 0 or r >= 2)."""
    if r == 1 or r < 0: raise LayoutError(f'{r}-byte gap')
    if r == 0: return []
    if r % 3 != 1: return [_filler(r)]
    return [_filler(2), _filler(r - 2)]


def build_tiled(raw, offsets, new):
    """Rebuild an MD file keeping every string at its original offset (so .ofs and any offset table
    compiled into the game stay valid). new: {string index: codes} for changed strings.
    The string area is tiled with dictionary entries; a changed string that doesn't fit its slot keeps
    as much of its text as fills the slot, then [dict ref, END] to an entry holding the rest, appended
    after the original data (2 codes per long string, 3 when the slot is 3k+1 bytes: a 2-byte filler).
    When every string is replaced, the original dictionary area (before the first string) is dead: if the
    code space runs out, it is refilled with rest entries instead (evmnng/evryokan: their Japanese used
    1,000-entry dictionaries).
    Raises LayoutError when the dictionary code space (base+ncmd .. 0xFFD) runs out."""
    try:
        return _build_tiled(raw, offsets, new, False)
    except LayoutError as ex:
        if len(new) < len(offsets) or 'dictionary entries' not in str(ex): raise
        return _build_tiled(raw, offsets, new, True)


def _build_tiled(raw, offsets, new, reuse_dict):
    base, ncmd, ndict = struct.unpack_from('>HHH', raw, 2)
    order = sorted(range(len(offsets)), key=lambda k: offsets[k])
    starts = [offsets[k] for k in order]
    assert starts == sorted(set(starts)), 'shared or unsorted offsets'
    d0 = i = 10 + 4 * ncmd
    for _ in range(ndict): _, i = codes_at(raw, i)
    assert i == starts[0], 'strings do not follow the dictionary'
    body = bytearray(raw[:starts[0]]); count = ndict; tail = []; stubs = {}
    if reuse_dict: count = None                  # region entries are counted once the rests are known
    ends = starts[1:] + [len(raw)]
    nslots = 0
    for k, s, e in zip(order, starts, ends):
        slot = e - s
        if k not in new:
            body += raw[s:e]; nslots += 1; continue
        packed = pack12(list(new[k]) + [END])
        if len(packed) > slot and slot < 3:
            raise LayoutError(f'string {k}: {slot}-byte slot cannot hold a stub')
        if len(packed) <= slot and slot - len(packed) != 1:
            body += packed; nslots += 1; rest = slot - len(packed)
        else:
            # head = the first codes of the text + [ref, END], exactly t bytes (pack12 sizes are 0 or 2 mod 3)
            t = slot - 2 if slot % 3 == 1 else slot
            n = 2 * t // 3 if t % 3 == 0 else (2 * t - 1) // 3
            h = max(0, min(n - 2, len(new[k]) - 1))
            while h and slot - len(pack12([0] * h + [0, END])) == 1: h -= 1
            head = list(new[k][:h])
            stubs[len(body)] = (k, head); body += b'\0' * len(pack12(head + [0, END])); nslots += 1
            rest = slot - len(pack12(head + [0, END]))
            tail.append((k, pack12(list(new[k][len(head):]) + [END])))
        f = _fillers(rest); body += b''.join(f); nslots += len(f)
    idx = {}
    if reuse_dict:
        # rests first fit into the old dictionary area [d0, first string), the remainder as one or two fillers
        room = starts[0] - d0; region = []; after = []
        for k, packed in tail:
            left = room - len(packed)
            if left >= 0 and left != 1: region.append((k, packed)); room = left
            else: after.append((k, packed))
        pos = d0
        for n, (k, packed) in enumerate(region):
            idx[k] = n; body[pos:pos + len(packed)] = packed; pos += len(packed)
        f = _fillers(room); body[pos:pos + room] = b''.join(f)
        count = len(region) + len(f) + nslots
        tail = after
    else:
        count += nslots
    for k, packed in tail:
        idx[k] = count; count += 1; body += packed
    limit = 0xFFD - base - ncmd
    if count > limit + 1: raise LayoutError(f'{count} dictionary entries > {limit + 1}')
    for pos, (k, head) in stubs.items():
        b = pack12(head + [base + ncmd + idx[k], END]); body[pos:pos + len(b)] = b
    struct.pack_into('>H', body, 6, count)
    return bytes(body)


def ofs_bytes(offs):
    return struct.pack(f'<{len(offs)}I', *offs), struct.pack(f'>{len(offs)}I', *offs)


def load_mesarc(mesdir_or_afs):
    """-> (font list, {name: (cmp_bytes, ofs_bytes)}) from an extracted MESARC dir."""
    files = sorted(os.listdir(mesdir_or_afs)); by = {f[5:]: f for f in files}
    rd = lambda n: open(os.path.join(mesdir_or_afs, by[n]), 'rb').read()
    font = load_font_table(os.path.join(mesdir_or_afs, by['font.cmp']))
    msgs = {}
    for f in files:
        if f.endswith('mes.cmp'):
            n = f[5:-4]; msgs[n] = (rd(n + '.cmp'), rd(n + '.ofs'))
    return font, msgs


def extract(mesdir, outdir):
    font, msgs = load_mesarc(mesdir); os.makedirs(outdir, exist_ok=True); n = 0
    for name, (cb, ob) in sorted(msgs.items()):
        offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
        md = MdFile(decompress(cb), offs)
        rows = [{'id': i, 'jp': codes_to_text(cs, md.base, md.cmds, font), 'en': ''} for i, cs in enumerate(md.strings)]
        with open(os.path.join(outdir, name + '.json'), 'w', encoding='utf-8') as g:
            json.dump({'file': name, 'strings': rows}, g, ensure_ascii=False, indent=1)
        n += len(rows)
    print(f'{len(msgs)} files, {n} strings -> {outdir}')


if __name__ == '__main__':
    if sys.argv[1] == 'extract': extract(sys.argv[2], sys.argv[3])
