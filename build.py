#!/usr/bin/env python3
"""Build build/namida_en.iso from rom/namida.iso + script/*.json.

Message files with no "en" string keep their original bytes, so an empty script gives a
byte-identical disc (the identity build). Translated files are re-encoded without a dictionary.
English is one character per glyph in a variable-width font: the game's ASCII glyphs (codes 0x00-0x5E)
are redrawn (tools/vwf.py) and the ELF advances them by a width table (tools/elfpatch.py).

usage: build.py [--out build/namida_en.iso] [--marker]
  --marker  replace every line with "[file:id]" + filler of the same cell count
"""
import argparse, json, os, re, struct, sys, time, hashlib
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import afs, iso, script, unpack, font as fontmod
import vwf, elfpatch, gfx, dllpatch, opening, evembed, ofs_patch
from cmp import decompress, compress

FONT_TEX = ['font_0000.tex', 'font_0001.tex', 'font_0002.tex', 'font_0003.tex']


def load_rows(name, use_en):
    rows = json.load(open(os.path.join(ROOT, 'script', name + '.json'), encoding='utf-8'))['strings']
    return rows if use_en else [dict(r, en='') for r in rows]


def load_qa(specs, files):
    """--qa FILE:ID=TEXT and --qa-file lines 'FILE:ID<tab>TEXT' (# comments) -> {(file, id): text}; '\\n' = newline."""
    out = {}
    items = [s.split('=', 1) for s in specs or []]
    for p in files or []:
        for line in open(p, encoding='utf-8'):
            line = line.rstrip('\n')
            if line.strip() and not line.startswith('#'): items.append(line.split('\t', 1))
    for key, text in items:
        name, i = key.rsplit(':', 1)
        out[(name if name.endswith('mes') else name + 'mes', int(i))] = text.replace('\\n', '\n')
    return out


def build_mesarc(od, md, marker=False, use_en=True, report=None, reencode=False, only=None, qa=None, ruler=None,
                 opening_captions=False):
    """reencode: rebuild every file from its Japanese text (no dictionary) - checks the container alone.
    opening_captions: append sc0001mes (.cmp/.ofs/.ofs.big) for the opening movie (tools/opening.py).
    only: regex; files not matching keep their original bytes (bisecting).
    qa: {(file, id): text} overrides (stress lines for measuring boxes; test builds only).
    ruler: [(regex, n)]: strings of matching files become digit rulers of n characters per line (ruler_text)."""
    qa = qa or {}; ruler = ruler or []
    for name in script.load_mesarc(md)[1]:
        n = next((n for rx, n in ruler if re.search(rx, name)), None)
        if n is None: continue
        for r in load_rows(name, use_en):
            if r['jp'] and (name, r['id']) not in qa: qa[(name, r['id'])] = ruler_text(name, r, n)
    font, msgs = script.load_mesarc(md)
    a = afs.Afs(os.path.join(od, 'MESARC.AFS'))
    members = [a.data(i) for i in range(len(a.ents))]

    # pass 1: which messages change
    plan = {}
    for name, (cb, ob) in sorted(msgs.items()):
        rows = load_rows(name, use_en)
        offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
        mdf = script.MdFile(decompress(cb), offs)
        assert len(rows) == len(mdf.strings), name
        selected = not only or re.search(only, name)
        if not selected: rows = [dict(r, en='') for r in rows]
        mk = marker and selected
        for r in rows:
            if (name, r['id']) in qa: r['qa'] = qa.pop((name, r['id']))
        if mk or (reencode and selected) or any(r['en'] or 'qa' in r for r in rows): plan[name] = (rows, mdf, mk)
    if qa: raise SystemExit(f'--qa: no such strings: {sorted(qa)}')
    if not plan:
        return afs.build(members, [a.meta(i) for i in range(len(a.ents))]), 0

    # English: one character per glyph, the game's own ASCII codes 0x00-0x5E redrawn (tools/vwf.py)
    enc_en = script.Encoder(font)
    relocated = []; moved = {}; built = {}
    for name, (rows, mdf, mk) in plan.items():
        cmds = list(mdf.cmds); new = {}
        for k, r in enumerate(rows):
            text = r['qa'] if 'qa' in r else marker_text(name, r) if mk else r['en']
            if text: new[k] = enc_en.encode(text, mdf.base, cmds, f'{name}[{r["id"]}]')
        if not new and not reencode: continue
        # Preferred: keep every string at its original offset. Several screens index strings with
        # offset tables compiled into the executable or DLLs (w_sy01 @ 0x5ca788 for wsy01mes, wmn01 menus,
        # see tools/ofs_tables.py); moving strings hangs or garbles them.
        try:
            if cmds != mdf.cmds: raise script.LayoutError('new command records')
            raw = script.build_tiled(mdf.raw, mdf.offsets, new)
        except script.LayoutError as ex:
            # Fallback (only big data files that fill the dictionary code space): relocate; these are
            # read through their .ofs (ItemMessNameGet etc.). Hardcoded tables for them: ofs_tables.py.
            strings = [new[k] if k in new else mdf.raw_for(k, len(cmds)) for k in range(len(rows))]
            # strings whose offset constant event scripts also use for something else stay put (tools/evembed.py)
            pins = evembed.pins(os.path.join(od, 'EVENTARC.AFS'), name, mdf.offsets)
            pins.update({k: mdf.offsets[k] for k in ofs_patch.PINS.get(name, ())})
            raw, new_offs = script.build_md(mdf.base, cmds, strings, () if len(new) == len(rows) else mdf.dict,
                                            pins=pins)
            lo, be = script.ofs_bytes(new_offs)
            members[a.index(name + '.ofs')] = lo
            members[a.index(name + '.ofs.big')] = be
            relocated.append(f'{name} ({ex})'); moved[name] = (mdf.offsets, new_offs)
        # files may grow past their original sectors: every read sizes itself from the AFS (docs/windows.md)
        members[a.index(name + '.cmp')] = compress(raw)
        built[name] = (mdf.raw, raw)

    # draw the VWF glyphs; their advances go into the ELF table (elfpatch.patch(widths=...))
    vf = vwf.VwfFont()
    texs = []
    for t in FONT_TEX:
        i = a.index(t); orig, img = fontmod.load_tex_bytes(members[i]); texs.append((i, orig, img))
    imgs = [img for _, _, img in texs]
    for g, ch in vwf.glyph_set(font):
        fontmod.put_glyph(imgs, g, vf.render(ch))
    for i, orig, img in texs:
        members[i] = fontmod.save_tex(orig, img)
    if report is not None:
        report.update(widths=vwf.width_table(vf, font), files=len(plan), relocated=relocated, moved=moved, built=built)
    metas = [a.meta(i) for i in range(len(a.ents))]
    if opening_captions:        # new files for the opening movie's captions (tools/opening.py)
        assert len(members) == opening.MESARC_N
        caps = opening.captions()
        raw, offs = script.build_md(0xA72, [], [enc_en.encode(c['en'], 0xA72, [], f'sc0001[{k}]')
                                               for k, c in enumerate(caps)])
        lo, be = script.ofs_bytes(offs)
        for ext, data in (('.cmp', compress(raw)), ('.ofs', lo), ('.ofs.big', be)):
            members.append(data); metas.append((opening.MES_NAME + ext).encode().ljust(32, b'\0') + metas[-1][32:])
        raw, offs = script.build_md(0xA72, [], [enc_en.encode(c['en'], 0xA72, [], f'card[{k}]')
                                               for k, c in enumerate(opening.cards()['cards'])])
        lo, be = script.ofs_bytes(offs)
        for ext, data in (('.cmp', compress(raw)), ('.ofs', lo), ('.ofs.big', be)):
            members.append(data); metas.append((opening.CARD_MES_NAME + ext).encode().ljust(32, b'\0') + metas[-1][32:])
        assert len(members) == opening.MESARC_N + opening.MESARC_ADDED
    return afs.build(members, metas), len(plan)


TOKEN = re.compile(r'(\{[^{}]*\})')


def ruler_text(name, r, n):
    """Measuring build: every prose line becomes digits (11 px each in the VWF) to n characters, the first one
    led by the string's id; tags ({name}..{name}, {choice}, {var}...) and line count stay as in the Japanese."""
    tag = f'{name.replace("mes", "")}:{r["id"]}|'; first = True; out_lines = []
    jp = re.sub(r'\{ruby:([^|}]*)\|[^}]*\}', r'\1', r['jp'])
    digits = '1234567890' * 20
    for line in jp.split('\n'):
        parts = TOKEN.split(line); out = []; in_name = False; prose = False
        for p in parts:
            if not p: continue
            if p.startswith('{'):
                if p == '{name}': in_name = not in_name
                out.append(p); continue
            if in_name: out.append('Spk'); continue
            prose = True
        if prose:
            head = tag if first else ''; first = False
            out.append(head + digits[:max(0, n - len(head))])
        out_lines.append(''.join(out))
    return '\n'.join(out_lines)


def marker_text(name, r):
    """Same lines, tags and cell count as the Japanese; prose replaced by '[file:id]' + filler,
    2 characters per original glyph, so each box shows its id at its full original width."""
    if not r['jp']: return ''                   # empty strings stay empty (2-byte slots)
    tag = f'[{name.replace("mes", "")}:{r["id"]}]'; first = True; out_lines = []
    jp = re.sub(r'\{ruby:([^|}]*)\|[^}]*\}', r'\1', r['jp'])
    for line in jp.split('\n'):
        parts = TOKEN.split(line); out = []; in_name = False
        for p in parts:
            if not p: continue
            if p.startswith('{'):
                t = p[1:-1]
                if t == 'name': in_name = not in_name
                out.append(p); continue
            if in_name: out.append('Spk'); continue
            n = 2 * len(p)
            if first:
                s = (tag + 'abcdefghijklmnopqrstuvwxyz' * 4)[:max(n, len(tag))]; first = False
            else:
                s = ('-' * n)
            out.append(s)
        out_lines.append(''.join(out))
    s = '\n'.join(out_lines)
    return s if not first else tag + ('\n' + s if s.strip() else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'namida_en.iso'))
    ap.add_argument('--marker', action='store_true')
    ap.add_argument('--debug', action='store_true', help='test build: pad mailbox for scripted input (tools/debugpatch.py)')
    ap.add_argument('--reencode', action='store_true', help='rebuild every message file from its Japanese text')
    ap.add_argument('--only', help='regex: only these message files change (bisecting)')
    ap.add_argument('--qa', action='append', metavar='FILE:ID=TEXT', help='override one string (measuring boxes)')
    ap.add_argument('--qa-file', action='append', metavar='PATH', help="override strings: lines 'FILE:ID<tab>TEXT'")
    ap.add_argument('--ruler', action='append', metavar='REGEX[:N]',
                    help='every string of matching files becomes an id-tagged digit ruler of N (default 50) characters per line')
    a = ap.parse_args()
    t0 = time.time()
    od, md = unpack.unpack()
    rep = {}
    mesarc, changed = build_mesarc(od, md, marker=a.marker, report=rep, reencode=a.reencode, only=a.only,
                                    qa=load_qa(a.qa, a.qa_file),
                                    ruler=[(s.rsplit(':', 1)[0], int(s.rsplit(':', 1)[1])) if re.search(r':\d+$', s)
                                           else (s, 50) for s in a.ruler or []], opening_captions=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    repl = {'/MESSAGE/MESARC.AFS': mesarc, **gfx.build_all(od)}   # text graphics (tools/gfx.py: WINARC, BTLARC, EFFARC)
    # map modules carry their own copy of the town's message file: NPCs read that one (tools/evembed.py)
    repl['/EVENT/EVENTARC.AFS'], elog = evembed.patch(os.path.join(od, 'EVENTARC.AFS'), rep['built'], rep.get('moved', {}))
    print(f'EVENTARC: {sum(1 for l in elog if "->" in l)} embedded message copies replaced; '
          + '; '.join(l for l in elog if 'rewritten' in l))
    da = afs.Afs(os.path.join(od, 'DATAARC.AFS'))                                        # opening captions' timing
    assert len(da.ents) == opening.DATAARC_N
    metas = [da.meta(i) for i in range(len(da.ents))]
    added = [(opening.ST_NAME, opening.timing())] + opening.card_timings()       # opening + title-card timings
    assert len(added) == opening.DATAARC_ADDED
    repl['/DATA/DATAARC.AFS'] = afs.build([da.data(i) for i in range(len(da.ents))] + [d for _, d in added],
                                          metas + [n.encode().ljust(32, b'\0') + metas[-1][32:] for n, _ in added])
    elf = elfpatch.patch(open(os.path.join(od, 'SLPM_659.52'), 'rb').read(), rep.get('widths'))
    if a.debug:
        import debugpatch
        elf = debugpatch.patch(elf)
    repl['/SLPM_659.52'] = dllpatch.patch_passwords(elf)
    repl.update(dllpatch.patch(lambda p: open(os.path.join(od, p[1:]), 'rb').read()))   # before ofs_patch reads them
    tlog = []
    if rep.get('moved'):
        repl.update(ofs_patch.patch(repl, rep['moved'], tlog))
        repl.update(ofs_patch.patch_imm(repl, rep['moved'], tlog))     # lui/ori offsets in switch code
    log = iso.patch(unpack.ISO, a.out, repl)
    with open(a.out, 'rb') as f: sha = hashlib.file_digest(f, 'sha1').hexdigest()
    rep.pop('moved', None)
    print(f'{changed} message files rebuilt; {len(rep.get("relocated", []))} relocated: '
          f'{", ".join(r.split(" (")[0] for r in rep.get("relocated", []))}')
    for line in tlog: print('  ' + line)
    print(f'disc: {log}')
    print(f'{a.out}  sha1 {sha}  {time.strftime("%H:%M:%S")}  ({time.time()-t0:.1f}s)')


if __name__ == '__main__':
    main()
