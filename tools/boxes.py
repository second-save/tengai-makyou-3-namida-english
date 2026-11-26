#!/usr/bin/env python3
"""Width gate: which box each script string is shown in, and its pixel budget (docs/windows.md).

usage: boxes.py lint [--all]     check every translated line (--all: also report strings with no measured box)
       boxes.py stats            how many strings each box covers, and how many have no box yet

Budgets are VWF pixels per line (vwf.text_width of the line with tags removed; {var}/{num} count 0, so lines
with runtime values need slack). Lines per box are not checked: dialogue and narration page every 2 lines.
Not measured yet (no box, so not linted): choice options after {choice} are checked as dialogue lines;
btl, mapld, shopd, rakuzad, staff, wki/wsh/wsy/wdj/wmn screens, sc, sg, mc, etc.
"""
import glob, json, os, re, sys
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# box: (px per line, max lines or None, status: docs/windows.md row)
BOXES = {
    'dialogue':   (440, None, 'measured'),     # ev*mes with a {name} speaker; 2 lines per page
    'narration':  (440, None, 'measured'),     # ev*mes without a speaker: 540 when centred narration, but the
                                               # same strings may open in the dialogue box; use the smaller
    'nameplate':  (136, 1, 'measured'),
    'item_name':  (210, 1, 'measured'),        # items menu list (shop list 230, details page 500)
    'item_kana':  (374, 1, 'guess'),           # JP max 17 glyphs; the ruler only showed the on-screen part
    'item_desc':  (590, 1, 'measured'),
    'item_lore':  (290, 4, 'measured'),
    'help':       (590, 1, 'measured'),        # top help bar of shops/menus
    'choice':     (400, None, 'measured'),     # choice panel option (text x 219 to the screen edge)
    'mon_name':   (230, 1, 'measured'),        # bestiary list (battle target bar 580)
    'skill_name': (185, 1, 'measured'),        # rank-up 新規技能/新規奥義 box (action banner ~300)
    'enemy_skill': (300, 1, 'measured'),       # enemy skills: shown only in the action banner
    'set_label':  (140, 1, 'measured'),        # 設定 row labels (options start at x ~252)
    'set_opt':    (95, 1, 'measured'),         # 設定 left option boxes (記憶する / ステレオ / 入)
    'set_opt_r':  (120, 1, 'measured'),        # 設定 right option boxes (記憶しない / モノラル / 切)
    'set_speed':  (25, 1, 'guess'),            # 速 / 遅 at the ends of the speed row: one short word or a symbol
    'place':      (264, 1, 'guess'),           # mapld names: JP max (12 glyphs). Real limit: the field menu joins
                                               # 国／地域／場所 into one ~335 px line; needs the region -> name map
    'shop_name':  (380, 1, 'measured'),        # shopd names (bottom bar)
    'song':       (440, 1, 'measured'),        # wdj01_04 song titles (music list)
    'building':   (220, 1, 'measured'),        # wdj01_01 building kinds (discard/break list, before the price)
    'mon_lore':   (320, 6, 'measured'),        # bestiary page 2, x 308 to the panel edge; a 7th line hits 種族
    'mon_place':  (390, 1, 'measured'),        # bestiary page 4: the ruler stopped after 36 characters (cap?)
    'mon_resist': (275, 2, 'measured'),        # 耐性 / 弱点 rows, x 352
    'confirm':    (420, 2, 'measured'),        # yes/no prompt (wsy02:51/52); JP 418
    'confirm_opt': (90, 1, 'measured'),        # yes/no options
}

TAG = re.compile(r'\{[^{}]*\}')
KANA = re.compile(r'[ぁ-ゖー・　 ]+')


def visible_lines(text):
    """Lines as drawn: speaker removed, ruby -> base text, other tags removed."""
    text = re.sub(r'\{name\}.*?\{name\}', '', text, flags=re.S)
    text = re.sub(r'\{ruby:([^|}]*)\|[^}]*\}', r'\1', text)
    return [TAG.sub('', l) for l in text.split('\n')]


def option_lines(text):
    """Indices of choice-option lines: the lines after a {choice} line, up to a {branch} line."""
    out = set(); on = False
    for i, l in enumerate(text.split('\n')):
        if '{branch}' in l: on = False
        elif on: out.add(i)
        if '{choice}' in l: on = True
    return out


def speaker(text):
    m = re.search(r'\{name\}(.*?)\{name\}', text, flags=re.S)
    return m.group(1) if m else None


def _item_kinds(rows):
    """itemdmes: name / kana reading / one-line description / lore, guessed from the Japanese."""
    k = []
    for r in rows:
        t = r['jp']
        k.append('' if not t else 'L' if t.count('\n') >= 2 else 'k' if KANA.fullmatch(re.sub(r'%s|[０-９Ａ-Ｚ]', '', t)) else 'n')  # %sこな, さくらじまのいし１
    out = []
    for i, c in enumerate(k):
        if c == 'L': out.append('item_lore')
        elif c == 'k': out.append('item_kana')
        elif c == 'n' and i + 1 < len(k) and k[i + 1] == 'k': out.append('item_name')
        elif c == 'n' and i > 0 and k[i - 1] == 'k': out.append('item_desc')
        elif c == 'n' and k[i + 1:i + 3] == ['n', 'L']: out.append('item_name')    # no reading row (半魂香)
        elif c == 'n' and i > 0 and out[i - 1] == 'item_name': out.append('item_desc')
        else: out.append(None)
    return out


FIXED = {('wsy02mes', 51): 'confirm', ('wsy02mes', 52): 'confirm', ('wsy02mes', 0): 'confirm_opt',
         ('wsy02mes', 1): 'confirm_opt', ('wsy02mes', 60): 'help', ('wsh01mes', 0): 'help', ('wmn01mes', 45): 'help'}


def _monster_kinds(rows):
    """btlmes records. Monsters: name, kana, lore (3+ lines), location (has ／), strengths, weaknesses.
    Techniques (btl 300+): name, kana, one-line effect, multi-line description. 奥義 (btl 0+): name, kana,
    effect, one-line description, multi-line lore. Only the names have a measured box so far."""
    out = [None] * len(rows)
    t = [r['jp'] for r in rows]
    one = lambda s: bool(s) and '\n' not in s
    i = 0
    while i < len(rows) - 3:
        if t[i] and KANA.fullmatch(t[i + 1] or 'x'):
            if i + 5 < len(rows) and '\n' in t[i + 2] and '／' in t[i + 3]:     # bosses have 2-line lore
                out[i:i + 6] = ['mon_name', None, 'mon_lore', 'mon_place', 'mon_resist', 'mon_resist']; i += 6; continue
            if i + 4 < len(rows) and one(t[i + 2]) and one(t[i + 3]) and '\n' in t[i + 4]:
                out[i] = 'skill_name'; i += 5; continue
            if one(t[i + 2]) and '\n' in t[i + 3]:
                out[i] = 'skill_name'; i += 4; continue
            if t[i].strip() and (not KANA.fullmatch(t[i]) or t[i] == t[i + 1]):  # enemy skill: name, reading, effect
                out[i] = 'enemy_skill'; i += 3; continue
        i += 1
    return out


def _name_kana(rows, name_box, kana_box, upto=None):
    """Files of (name, kana reading) pairs."""
    out = [None] * len(rows)
    for i in range(len(rows) - 1):
        if upto is not None and i >= upto: break
        if rows[i]['jp'] and KANA.fullmatch((rows[i + 1]['jp'] or 'x').rstrip('？')) and out[i] is None:  # みわくじょう？
            out[i], out[i + 1] = name_box, kana_box
    return out


SETTINGS = {**{i: 'set_label' for i in (162, 164, 173, 177, 181, 185)},
            **{i: 'set_opt' for i in (175, 179, 183)}, **{i: 'set_opt_r' for i in (176, 180, 184)},
            166: 'set_speed', 172: 'set_speed',
            **{i: 'help' for i in (163, 165, 174, 178, 182)}}


def classify(name, rows):
    """-> [box or None] per row."""
    if name == 'itemdmes': return _item_kinds(rows)
    if name == 'btlmes': return _monster_kinds(rows)
    if name == 'mapldmes':   # {btn:0a} rows: destination list (unmeasured), same names as the place rows
        return [b or ('place' if (r['jp'] or '').startswith('{btn:0a}') else None)
                for b, r in zip(_name_kana(rows, 'place', None), rows)]
    if name == 'wdj01_04mes': return _name_kana(rows, 'song', None, upto=194)
    if name == 'wdj01_01mes': return _name_kana(rows, 'building', None)
    if name == 'shopdmes': return ['shop_name' if r['jp'] and '\n' not in r['jp'] else None for r in rows]
    if name == 'wmn01mes': return [SETTINGS.get(r['id'], FIXED.get((name, r['id']))) for r in rows]
    out = []
    for r in rows:
        if (name, r['id']) in FIXED: out.append(FIXED[(name, r['id'])])
        elif re.fullmatch(r'ev\w+mes', name):       # ev0100mes scenes, evm<map>mes NPCs, evryokanmes
            out.append('dialogue' if speaker(r['jp']) is not None else 'narration')
        else: out.append(None)
    return out


@lru_cache(None)
def _font():
    import vwf
    return vwf.VwfFont()


def width(s):
    import vwf
    return vwf.text_width(_font(), s)


def check(name, rows, field='en', only=None):
    """-> list of problems (file, id, box, message) for the given text field; only=row id lints just that row."""
    probs = []
    for r, box in zip(rows, classify(name, rows)):
        t = r.get(field) or ''
        if not t or box is None or (only is not None and r['id'] != only): continue
        px, maxl, _ = BOXES[box]
        lines = visible_lines(t)
        opts = option_lines(t)       # choice options go in the choice panel
        for i, l in enumerate(lines):
            b, p = ('choice', BOXES['choice'][0]) if i in opts else (box, px)
            w = width(l)
            if w > p: probs.append((name, r['id'], b, f'line {i + 1}: {w} px > {p}: {l!r}'))
        if maxl and len(lines) > maxl: probs.append((name, r['id'], box, f'{len(lines)} lines > {maxl}'))
        sp = speaker(t)
        if sp is not None and width(sp) > BOXES['nameplate'][0]:
            probs.append((name, r['id'], 'nameplate', f'{width(sp)} px > {BOXES["nameplate"][0]}: {sp!r}'))
    return probs


def load_all():
    for p in sorted(glob.glob(os.path.join(ROOT, 'script', '*.json'))):
        d = json.load(open(p, encoding='utf-8'))
        yield d['file'], d['strings']


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'lint'
    if cmd == 'stats':
        from collections import Counter
        c = Counter(); n = 0
        for name, rows in load_all():
            for r, b in zip(rows, classify(name, rows)):
                if r['jp']: c[b or f'(none) {re.sub(r"[0-9_]+.*", "", name)}'] += 1; n += 1
        for b, k in c.most_common(): print(f'{k:6d}  {b}')
        print(f'{n} non-empty strings')
        return
    probs = [p for name, rows in load_all() for p in check(name, rows)]
    for p in probs: print(*p, sep='  ')
    print(f'{len(probs)} width problems')
    sys.exit(1 if probs else 0)


if __name__ == '__main__':
    main()
