#!/usr/bin/env python3
"""Translation batches (docs/translator-brief.md): split untranslated text, check translator output, merge it back.

    batches.py split [--size 3500] [--only REGEX] [--held]
                                                    work/tl/bNNN.tsv + work/tl/bNNN.terms.txt, untranslated JP
                                                    (--held: include the HELD puzzle files)
    batches.py check [bNNN ...]                     a batch's .out.tsv; with no batch, all shipped English
    batches.py merge bNNN ... [--overwrite] [--unmeasured-ok]
                                                    check, then write the English into script/; --unmeasured-ok lets
                                                    lines over a JP-size budget through, logged in docs/qa-unmeasured.md
    batches.py fit "text" [--box dialogue]          pixel width per line (\\n = line break)
    batches.py fill-readings                        kana-reading rows get their name's English (decision D9)
    batches.py terms                                rewrite every batch's terms file from glossary.md
    batches.py pairs bNNN ...                       work/tl/review_bFIRST-bLAST.txt for a reviewer (JP/EN, +-2 lines)

Adapted from the skill's assets/batches.py. Ids are FILE:N (file without "mes"). In the TSVs a line break is the
two characters \\n. Batch TSV: id, speaker, box, limit (px per line), JP. Output: work/tl/bNNN.out.tsv, id<TAB>English.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import boxes

TL = ROOT / 'work/tl'
GLOSSARY = ROOT / 'glossary.md'
UNMEASURED = ROOT / 'docs/qa-unmeasured.md'    # merged lines over a JP-size budget: check them in game
MAX_ENTRIES = 150
TAG = re.compile(r'\{[^{}]*\}')
RUBY = re.compile(r'\{ruby:([^|}]*)\|[^}]*\}')
VARIABLE = r'\{(?:var|num)\}'
# text the game may compare or count (docs/synopsis.md, Mechanics): kept out of batches until checked in game.
# shortcut: whole files held back, though only some lines are puzzle text; split them by line once the checks are done
HELD = re.compile(r'^(ev0209|ev0324|ev0622|ev0623|ev0941|ev0997|ev1005|ev2520|ev4002|ev4007|ev4012|ev4025|ev4037|ev4038)mes$')
# name + kana-reading pairs: the reading row is not translated, it repeats the name's English (D9)
# strings whose tags change on purpose, with code to match: wmn01:63 = the field-menu location line, which prints
# location/area only (elfpatch 'location a1-a3', ws_place_printf) because country/location/area overflowed the box
TAGS_CHANGED = {'wmn01:63'}
READING_FILES ={'itemdmes', 'btlmes', 'mapldmes', 'wdj01_04mes', 'wdj01_01mes'}


def is_reading(name, rows, i):
    if name not in READING_FILES or not i: return False
    t, p = rows[i]['jp'], rows[i - 1]['jp']
    if i + 1 < len(rows) and rows[i + 1]['jp'] == t: return False    # hiragana name + identical reading (ひっかき)
    return bool(t) and bool(boxes.KANA.fullmatch(t)) and bool(p) and '\n' not in p and not boxes.KANA.fullmatch(p)


def files():
    for path in sorted((ROOT / 'script').glob('*.json')):
        yield path, json.loads(path.read_text(encoding='utf-8'))


def index():
    """{id: entry}; entry: file, rows, i, jp, en, box, speaker, reading."""
    out = {}
    for _, d in files():
        name, rows = d['file'], d['strings']
        for i, (r, box) in enumerate(zip(rows, boxes.classify(name, rows))):
            out[f"{name[:-3]}:{r['id']}"] = dict(file=name, rows=rows, i=i, jp=r['jp'], en=r['en'], box=box,
                                                 speaker=boxes.speaker(r['jp']) or '', reading=is_reading(name, rows, i))
    return out


def tags(text):
    """Tags that must survive translation; ruby is dropped in English (D9)."""
    return Counter(TAG.findall(RUBY.sub(r'\1', text)))


def esc(s): return s.replace('\n', '\\n')
def unesc(s): return s.replace('\\n', '\n')


def kind(c):
    if '぀' <= c <= 'ゟ': return 'h'
    if '゠' <= c <= 'ヿ': return 'k'
    if '一' <= c <= '鿿' or c == '々': return 'K'
    return 'o'


def has_term(jp, term):
    """term occurs as a whole kana or kanji run: ミン isn't in タイミング."""
    for m in re.finditer(re.escape(term), jp):
        a, b = m.start(), m.end()
        if (a == 0 or kind(jp[a - 1]) != kind(term[0])) and (b == len(jp) or kind(jp[b]) != kind(term[-1])):
            return True
    return False


def glossary():
    """[(JP forms, EN forms, avoid forms)] from glossary.md's | JP | EN | max | notes | Avoid | tables."""
    rows = []
    for line in GLOSSARY.read_text(encoding='utf-8').splitlines():
        c = [x.strip() for x in line.strip().strip('|').split('|')]
        if line.startswith('|') and len(c) >= 2 and c[0] not in ('JP', '') and not set(c[0]) <= set('-: '):
            avoid = [x.strip() for x in c[4].split('/') if x.strip()] if len(c) > 4 else []
            rows.append(([x.strip() for x in c[0].split('/')], [x.strip() for x in c[1].split('/')], avoid))
    return rows


def problems(e, en, terms):
    if not e['jp'].strip(): return []           # JP is only a break or a full-width space (btl:4415): nothing to translate
    if not en.strip(): return ['empty English']
    out = []
    plain = TAG.sub('', en)
    if bad := sorted({c for c in plain if not (' ' <= c <= '~') and c != '\n'} | ({'{', '}'} & set(plain))):
        out.append(f'characters the font lacks {bad}')
    if '\t' in en or re.search(r'\\u[0-9a-fA-F]{4}', en): out.append('tab or escape sequence')
    if tags(e['jp']) != tags(en): out.append(f"tags differ: JP {dict(tags(e['jp']))} EN {dict(tags(en))}")
    # {var}/{num} are filled by position: a swapped pair hands the game a number as a string pointer (crash, etcmes:21)
    var_order = lambda s: re.findall(r'\{(var|num)\b', s)
    if var_order(e['jp']) != var_order(en) and tags(e['jp']) == tags(en):
        out.append(f"variable order differs: JP {var_order(e['jp'])} EN {var_order(en)}")
    if re.search(VARIABLE + r'(st|nd|rd|th)\b', en): out.append('ordinal suffix after a variable (write "No. {num}")')
    jp_plain = TAG.sub(' ', RUBY.sub(r'\1', e['jp']))      # ' ': the speaker doesn't run into the text
    # longest terms first, each blanked once matched: 壱与の母 (Mother) doesn't also demand 壱与 (Ichiyo)
    for jps, ens, avoid in sorted(terms, key=lambda t: -max(map(len, t[0]))):
        if any(has_term(jp_plain, j) for j in jps):
            flat = re.sub(r'\s+', ' ', en.replace('\\n', ' ')).lower()   # a name may wrap: Golden\nTemple
            if not any(x.lower() in flat for x in ens): out.append(f'glossary: {jps[0]} -> {ens[0]}')
            for j in jps: jp_plain = jp_plain.replace(j, '〓')
            # only where the term is in the JP: "gold" is banned for 両, not for a golden statue
            out += [f'glossary Avoid: {a}' for a in avoid if re.search(rf'\b{re.escape(a)}\b', en)]
    if e['box'] is None:        # no measured box: the Japanese box size is the budget (22 px a glyph, same line count)
        jl, el = boxes.visible_lines(e['jp']), boxes.visible_lines(en)
        cap = 22 * max(map(len, jl))
        out += [f'line {i + 1}: {boxes.width(l)} px > {cap} (the JP width; no measured box)'
                for i, l in enumerate(el) if boxes.width(l) > cap]
        if len(el) > len(jl): out.append(f'{len(el)} lines > {len(jl)} (the JP line count; no measured box)')
    row = dict(e['rows'][e['i']], en=en)
    rows = e['rows'][:e['i']] + [row] + e['rows'][e['i'] + 1:]
    out += [p[3] if p[2] == e['box'] else f'{p[2]}: {p[3]}'
            for p in boxes.check(e['file'], rows, only=row['id'])]
    return out


def read_tsv(path):
    return [l.split('\t') for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def existing(): return sorted(TL.glob('b[0-9][0-9][0-9].tsv'))


def split(size, only=None, held=False):
    """Numbers on from the last batch and skips ids already batched, so a repeat run can't duplicate work.
    held: include the HELD puzzle files (once their mechanics are checked)."""
    TL.mkdir(parents=True, exist_ok=True)
    taken = {r[0] for p in existing() for r in read_tsv(p)}
    n = max((int(p.stem[1:]) for p in existing()), default=0)
    batches, cur, chars, last = [], [], 0, None
    for eid, e in index().items():
        if not e['jp'] or e['en'] or e['reading'] or eid in taken or (HELD.match(e['file']) and not held): continue
        if only and not re.search(only, e['file']): continue
        c = len(TAG.sub('', e['jp']))
        # a new file starts a new batch once the current one is half full, so scenes stay whole where they can
        if cur and (chars + c > size or len(cur) >= MAX_ENTRIES or (e['file'] != last and chars > size // 2)):
            batches.append(cur); cur, chars = [], 0
        cur.append((eid, e)); chars += c; last = e['file']
    if cur: batches.append(cur)
    for b in batches:
        n += 1; name = f'b{n:03d}'
        path = TL / f'{name}.tsv'
        if path.exists(): sys.exit(f'{path} already exists')
        path.write_text(''.join(f"{i}\t{e['speaker']}\t{e['box'] or ''}\t{boxes.BOXES[e['box']][0] if e['box'] else ''}"
                                f"\t{esc(e['jp'])}\n" for i, e in b), encoding='utf-8', newline='\n')
        write_terms(name)
    print(f'{len(batches)} new batches in {TL}, {len(taken)} ids already batched')


def write_terms(name, terms=None):
    """work/tl/NAME.terms.txt: the glossary rows whose JP occurs in the batch (rerun after glossary edits)."""
    terms = glossary() if terms is None else terms
    jps = ' '.join(RUBY.sub(r'\1', r[-1]) for r in read_tsv(TL / f'{name}.tsv'))
    used = [f'{j}\t{ens[0]}\n' for jl, ens, _ in terms for j in jl if has_term(jps, j)]
    (TL / f'{name}.terms.txt').write_text(''.join(used) or '(no glossary terms in this batch)\n',
                                          encoding='utf-8', newline='\n')


def check_batch(batch, entries, terms):
    want = [r[0] for r in read_tsv(TL / f'{batch}.tsv')]
    rows = [(r[0], unesc('\t'.join(r[1:]))) for r in read_tsv(TL / f'{batch}.out.tsv')]
    bad = []
    got = [r[0] for r in rows]
    if got != want:
        dup = sorted(i for i, c in Counter(got).items() if c > 1)
        bad.append(f'ids differ: missing {sorted(set(want) - set(got))[:8]} extra {sorted(set(got) - set(want))[:8]} '
                   f'duplicate {dup[:8]} (order must match too)')
    for eid, en in rows:
        if eid in entries: bad += [f'{eid}: {p}: {esc(en)!r}' for p in problems(entries[eid], en, terms)]
    return bad, dict(rows)


def write_back(new, overwrite=False):
    """new: {id: en}. Refuses to replace different English unless told to, before anything is written."""
    todo = []
    for path, d in files():
        pre = d['file'][:-3]; touched = False
        for r in d['strings']:
            v = new.get(f"{pre}:{r['id']}")
            if v is None or r['en'] == v: continue
            if r['en'] and not overwrite: sys.exit(f"{pre}:{r['id']} would lose {r['en']!r}: pass --overwrite if meant")
            r['en'] = v; touched = True
        if touched: todo.append((path, d))
    for path, d in todo:
        path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    return len(todo)


def pairs(names, entries, ctx=2):
    """Reviewer input: '>> id | JP' / 'EN' per batch entry, +-ctx neighbours of the same file as context."""
    out = []
    for b in names:
        en = dict(check_batch(b, entries, [])[1])
        out.append(f'## {b}\n')
        for r in read_tsv(TL / f'{b}.tsv'):
            e = entries[r[0]]; rows, i, pre = e['rows'], e['i'], r[0].split(':')[0]
            for j in range(max(0, i - ctx), min(len(rows), i + ctx + 1)):
                jid = f"{pre}:{rows[j]['id']}"
                if j != i and jid in en: continue    # a batch entry: printed in its own turn
                mark = '>>' if j == i else '  '
                text = en.get(jid) if j == i else rows[j]['en']
                out.append(f"{mark} {jid} | {esc(rows[j]['jp'])}\n   {esc(text or '')}\n")
            out.append('\n')
    return ''.join(out)


def fill_readings():
    """Each kana-reading row repeats its name's English (the field also shows on screen; D9)."""
    new = {i: e['rows'][e['i'] - 1]['en'] for i, e in index().items()
           if e['reading'] and e['rows'][e['i'] - 1]['en'] and not e['en']}
    print(f'{len(new)} readings filled in {write_back(new)} files')


def main(argv):
    if not argv: sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == 'split':
        opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d
        return split(int(opt('--size', 3500)), opt('--only'), '--held' in args)
    if cmd == 'fit':
        box = args[args.index('--box') + 1] if '--box' in args else 'dialogue'
        for l in boxes.visible_lines(unesc(args[0])):
            print(f'{boxes.width(l):4d} / {boxes.BOXES[box][0]}  {l}')
        return 0
    if cmd == 'fill-readings': return fill_readings()
    if cmd == 'terms':
        t = glossary()
        for p in existing(): write_terms(p.stem, t)
        return print(f'terms rewritten for {len(existing())} batches')
    overwrite, unmeasured = '--overwrite' in args, '--unmeasured-ok' in args
    names = [a for a in args if not a.startswith('--')]
    entries, terms = index(), glossary()
    if cmd == 'check' and not names:
        bad = [f'{i}: {p}' for i, e in entries.items() if e['en'] and not e['reading'] for p in problems(e, e['en'], terms)
               if not (p.startswith('tags differ') and i in TAGS_CHANGED)]
        guess = [b for b in bad if 'no measured box' in b]    # merged with --unmeasured-ok, listed in docs/qa-unmeasured.md
        bad = [b for b in bad if 'no measured box' not in b]
        print(f'{sum(bool(e["en"]) for e in entries.values())} translated, {len(bad)} problems, '
              f'{len(guess)} over a JP-size guess (docs/qa-unmeasured.md)')
        print('\n'.join(bad[:200]))
        return 1 if bad else 0
    if cmd == 'pairs' and names:
        out = TL / f'review_{names[0]}-{names[-1]}.txt'
        out.write_text(pairs(names, entries), encoding='utf-8', newline='\n')
        return print(out)
    if cmd not in ('check', 'merge') or not names: sys.exit(__doc__)
    new, failed, waived = {}, 0, []
    for b in names:
        bad, rows = check_batch(b, entries, terms)
        if unmeasured:      # the JP-size budget is a guess: merge, and log the line for in-game QA
            waived += [l for l in bad if 'no measured box' in l]
            bad = [l for l in bad if 'no measured box' not in l]
        new.update(rows); failed += bool(bad)
        print(f'{b}: ' + ('OK' if not bad else f'{len(bad)} problems'))
        for l in bad: print('  ' + l)
    if failed: return 1
    if cmd == 'merge':
        print(f'merged into {write_back(new, overwrite)} files')
        if waived:
            with open(UNMEASURED, 'a', encoding='utf-8') as f: f.write(''.join(f'- {l}\n' for l in waived))
            print(f'{len(waived)} lines over a JP-size budget logged in {UNMEASURED}')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv[1:]))
