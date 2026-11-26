#!/usr/bin/env python3
"""Event scripts (ev*mes) in story order as plain text chunks for synopsis / story reviewers.

usage: story_export.py [OUTDIR]   (default work/story) -> one file per chunk: '## evNNNN' headers, 'id<TAB>line',
       ruby reduced to its kanji, line breaks as ' / '.
"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# chunk -> scene-number prefix regex (ev0100..ev0135 = chapter 1 ...); sizes 20-55k JP characters each
CHUNKS = {'a': '0[1-3]', 'b': '04', 'c': '0[57]', 'd': '06[0-4]', 'e': '06[5-9]', 'f': '08', 'g': '09|10',
          'h': '[2-9][0-9]'}


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'work', 'story')
    os.makedirs(out_dir, exist_ok=True)
    for chunk, pat in CHUNKS.items():
        lines = []
        for f in sorted(glob.glob(os.path.join(ROOT, 'script', 'ev[0-9]*.json'))):
            num = re.search(r'ev(\d+)mes', f).group(1).zfill(4)     # ev100mes (empty) sorts as 0100
            if not re.match(f'({pat})', num): continue
            lines.append(f'## ev{num}')
            for s in json.load(open(f, encoding='utf-8'))['strings']:
                if s['jp']:
                    text = re.sub(r'\{ruby:([^|}]*)\|[^}]*\}', r'\1', s['jp'])
                    lines.append(f"{s['id']}\t" + ' / '.join(text.split('\n')))
        with open(os.path.join(out_dir, f'{chunk}.txt'), 'w', encoding='utf-8') as g:
            g.write('\n'.join(lines) + '\n')
        print(chunk, sum(map(len, lines)))


if __name__ == '__main__':
    main()
