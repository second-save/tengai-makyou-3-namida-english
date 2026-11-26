#!/usr/bin/env python3
"""Find runs of Shift-JIS text in a binary. usage: sjis_scan.py FILE [minchars]"""
import sys, re
d = open(sys.argv[1], 'rb').read(); mn = int(sys.argv[2]) if len(sys.argv) > 2 else 4
pat = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e])+')
for m in pat.finditer(d):
    s = m.group()
    try: t = s.decode('cp932')
    except UnicodeDecodeError: continue
    if sum(1 for c in t if ord(c) > 0x3000) >= mn:
        print(f'{m.start():#08x} {t}')
