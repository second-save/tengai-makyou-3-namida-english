#!/usr/bin/env python3
"""Find copies of message-file offset tables hardcoded in the executable and DLLs.

Some screens ignore *.ofs and index strings with offsets compiled into the code (w_sy01 loops over
23 offsets at 0x5ca788 for wsy01mes). Every such copy must be rewritten when a file is rebuilt.
Matches >= MIN consecutive offsets of one file (LE or BE), anywhere in the binary.

usage: ofs_tables.py [--min 3]  -> work/ofs_tables.json  {file: [[binary, file_offset, first_index, count, endian]]}
"""
import json, os, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MES = os.path.join(ROOT, 'work', 'mes')
BINS = [os.path.join(ROOT, 'work', 'orig', 'SLPM_659.52')]
for dp, _, fs in os.walk(os.path.join(ROOT, 'work', 'orig', 'DLL')):
    BINS += [os.path.join(dp, f) for f in fs]


def scan(min_run=3):
    bins = {os.path.relpath(b, ROOT): open(b, 'rb').read() for b in sorted(BINS)}
    out = {}
    for f in sorted(os.listdir(MES)):
        if not f.endswith('mes.ofs'): continue
        name = f[5:-4]; raw = open(os.path.join(MES, f), 'rb').read()
        offs = list(struct.unpack(f'<{len(raw)//4}I', raw))
        if len(offs) < min_run: continue
        for bn, data in bins.items():
            for endian in '<>':
                for k in range(len(offs) - min_run + 1):
                    pat = struct.pack(f'{endian}{min_run}I', *offs[k:k + min_run])
                    i = data.find(pat)
                    while i >= 0:
                        n = min_run
                        while k + n < len(offs) and data[i + 4 * n:i + 4 * n + 4] == struct.pack(endian + 'I', offs[k + n]): n += 1
                        hit = [bn, i, k, n, endian]
                        if not any(h[0] == bn and h[1] <= i < h[1] + 4 * h[3] for h in out.get(name, [])):
                            out.setdefault(name, []).append(hit)
                        i = data.find(pat, i + 4)
    return out


if __name__ == '__main__':
    mn = int(sys.argv[sys.argv.index('--min') + 1]) if '--min' in sys.argv else 3
    res = scan(mn)
    json.dump(res, open(os.path.join(ROOT, 'work', 'ofs_tables.json'), 'w'), indent=1)
    for k, v in res.items():
        for h in v: print(k, h)
