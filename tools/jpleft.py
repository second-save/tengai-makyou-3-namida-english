#!/usr/bin/env python3
"""Leftover-Japanese scan of a built disc, in the game's own text encoding (12-bit glyph codes, tools/script.py).

Decodes every string the game can read, as it reads it, and reports the ones that still contain kana or kanji:
  - MESARC: every message file through its .ofs (dictionary references expanded)
  - EVENTARC: the message copy embedded in each map module (tools/evembed.py), through the same offsets
Strings whose Japanese is kept on purpose are listed in KEEP (file:id -> reason).

usage: jpleft.py [ISO] [--all]   (default build/namida_en.iso; --all also prints every hit's text)
"""
import os, re, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs, evembed, iso, script, unpack
from cmp import decompress

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JP = re.compile(r'[぀-ヿ㐀-鿿ｦ-ﾟ]')
KEEP = {}


def extract(iso_path, paths, d):
    with open(iso_path, 'rb') as f:
        disc = iso.Disc(f)
        for p in paths:
            e = disc.files[p]; f.seek(e.lba * 2048)
            open(os.path.join(d, os.path.basename(p)), 'wb').write(f.read(e.size))


def text(cs, md, font):
    return script.codes_to_text(cs, md.base, md.cmds, font)


def scan(iso_path):
    """-> [(where, file, id, text)] strings with kana/kanji in the built disc."""
    od, mdir = unpack.unpack(verify=False)
    font, msgs = script.load_mesarc(mdir)
    hits = []
    with tempfile.TemporaryDirectory() as d:
        extract(iso_path, ['/MESSAGE/MESARC.AFS', '/EVENT/EVENTARC.AFS'], d)
        mes = afs.Afs(os.path.join(d, 'MESARC.AFS'))
        built = {}
        for n in mes.names:
            if not n.endswith('mes.cmp'): continue
            name = n[:-4]
            ofs = mes.data(mes.index(name + '.ofs'))
            offs = list(struct.unpack(f'<{len(ofs) // 4}I', ofs))
            raw = decompress(mes.data(mes.index(n))); built[name] = (raw, offs)
            md = script.MdFile(raw, offs)
            for k, cs in enumerate(md.strings):
                t = text(cs, md, font)
                if JP.search(re.sub(r'\{[^}]*\}', '', t)): hits.append(('MESARC', name, k, t))
        by_raw = {decompress(msgs[n][0]): n for n in msgs}            # original embedded copies -> their file
        ev = afs.Afs(os.path.join(d, 'EVENTARC.AFS'))
        for i, mod_name in enumerate(ev.names):
            data = ev.data(i)
            if data[:4] != b'CMP\0': continue
            mod = decompress(data); e = evembed.embedded(mod)
            if not e: continue
            p, n = e
            emb = mod[p:]
            name = next((nm for nm, (raw, _) in built.items() if emb[:len(raw)] == raw), None)
            if name: continue                                         # identical to the built MESARC file: done above
            orig = next((nm for raw, nm in by_raw.items() if emb[:len(raw)] == raw and len(raw) > 10), None)
            if orig is None: hits.append(('EVENTARC', mod_name, -1, 'embedded message copy matches no file')); continue
            md = script.MdFile(emb, built[orig][1] if orig in built else
                               list(struct.unpack(f'<{len(msgs[orig][1]) // 4}I', msgs[orig][1])))
            for k, cs in enumerate(md.strings):
                t = text(cs, md, font)
                if JP.search(re.sub(r'\{[^}]*\}', '', t)): hits.append((f'EVENTARC {mod_name}', orig, k, t))
    return [h for h in hits if f'{h[1]}:{h[2]}' not in KEEP]


if __name__ == '__main__':
    a = sys.argv[1:]
    iso_path = next((x for x in a if not x.startswith('--')), os.path.join(ROOT, 'build', 'namida_en.iso'))
    hits = scan(iso_path)
    from collections import Counter
    print(f'{len(hits)} strings with Japanese')
    for (w, f), c in sorted(Counter((h[0], h[1]) for h in hits).items()): print(f'  {c:5d}  {w}  {f}')
    for h in hits if '--all' in a else hits[:60]:
        print(f'{h[0]} {h[1]}:{h[2]}  {h[3][:90]!r}')
