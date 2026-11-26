#!/usr/bin/env python3
"""Rewrite hardcoded string-offset tables for message files the build had to relocate.

Most message files keep every string at its original offset (script.build_tiled), so tables compiled
into the game stay valid. The few big files that don't fit that layout get new offsets; any copy of
their old offsets inside SLPM_659.52 or a DLL (found by ofs_tables.py) is rewritten here.
Filters against coincidental matches:
  - little-endian, 4-aligned runs of >= 3 consecutive offsets only
  - not an arithmetic sequence that keeps going past the match (e.g. SG002 0x52dc, 0x52e4, ... step 8)
  - not overlapping a longer match of a file that was NOT relocated (that table belongs to it)
Tables of fewer than 3 entries can't be found this way: QA the screens of relocated files.
patch_imm does the same for offsets built in code with lui/ori (see imm_runs, SINGLES).
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ofs_tables

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'work', 'ofs_tables.json')
# disc path of each scanned binary
DISC = {'work/orig/SLPM_659.52': '/SLPM_659.52'}


def disc_path(rel):
    if rel in DISC: return DISC[rel]
    assert rel.startswith('work/orig/DLL/'), rel
    return '/' + rel[len('work/orig/'):].upper()


def tables():
    if not os.path.isfile(CACHE):
        json.dump(ofs_tables.scan(3), open(CACHE, 'w'), indent=1)
    return json.load(open(CACHE))


def _arith_continues(data, i, n):
    vals = struct.unpack_from(f'<{n}I', data, i)
    step = vals[1] - vals[0]
    if any(vals[j + 1] - vals[j] != step for j in range(n - 1)): return False
    after = struct.unpack_from('<I', data, i + 4 * n)[0] if i + 4 * n + 4 <= len(data) else None
    before = struct.unpack_from('<I', data, i - 4)[0] if i >= 4 else None
    return after == vals[-1] + step or before == vals[0] - step


I_DEST = {0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19, 0x1A, 0x1B, 0x1E,   # ALU-immediate, lq
          0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37}                         # loads


def _writes(x, r):
    """Does instruction x (roughly) write GPR r?"""
    op = x >> 26
    if op == 0: return (x >> 11) & 31 == r and x & 0x3F not in (0x08, 0x18, 0x19, 0x1A, 0x1B)  # not jr/mult/div
    if op == 0x03: return r == 31                                                                # jal
    if op in I_DEST: return (x >> 16) & 31 == r
    return False


def imm_pairs(data, window=8):
    """-> [(lui pos, lo pos, kind 'ori'|'addiu', value)] for `lui rt,H` followed within `window` instructions by
    `ori/addiu rt,rt,L` with no write to rt in between (code that builds a 32-bit constant; the low half is
    often in a jal delay slot 3-4 instructions later)."""
    out = []
    n = len(data) // 4
    for k in range(n):
        w, = struct.unpack_from('<I', data, 4 * k)
        if w >> 26 != 0x0F: continue
        rt, hi = (w >> 16) & 31, w & 0xFFFF
        if rt == 0: continue
        for m in range(k + 1, min(n, k + 1 + window)):
            x, = struct.unpack_from('<I', data, 4 * m)
            op, rs, rt2, lo = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
            if rs == rt and rt2 == rt and op in (0x0D, 0x09):
                v = (hi << 16) + (lo if op == 0x0D else lo - 0x10000 * (lo >= 0x8000))
                out.append((4 * k, 4 * m, 'ori' if op == 0x0D else 'addiu', v & 0xFFFFFFFF)); break
            if _writes(x, rt): break
    return out


def imm_runs(data, old, min_run=3, window=0x100):
    """Runs of >= min_run constant pairs building consecutive old offsets (string k, k+1, ...) of one file,
    each pair within `window` bytes of the previous: switch statements that return message offsets
    (e.g. the bestiary race names, btlmes 4477+, built at 0x1c8860)."""
    idx = {}
    for i, o in enumerate(old): idx.setdefault(o, i)
    hits = [(p, q, kind, idx[v]) for p, q, kind, v in imm_pairs(data) if v in idx and v >= 0x100]
    runs, cur = [], []
    for h in hits:
        if cur and h[0] - cur[-1][0] <= window and h[3] == cur[-1][3] + 1: cur.append(h)
        else:
            if len(cur) >= min_run: runs.append(cur)
            cur = [h]
    if len(cur) >= min_run: runs.append(cur)
    return runs


# Single lui/ori constants trusted without a run: btlmes battle messages (4400+) are built that way all over the
# battle code (BTLCheckAtkPlayer, SpReEntrySpKindEff, BTLWin*...: 2026-11-19 audit, every hit >= 4400 was in
# BTL/Sp/Boss code; hits below 4400 were RenderWare constants). Main executable only.
SINGLES = {'btlmes': 4400}
# single `addiu rX, zero, off` loads of one string's offset (ELF file offset -> string index), found by searching the
# old offsets: the map screen's 現在地 label and its reading (mapld:15/16) showed garbage once mapld was relocated.
LI_SITES = {'mapldmes': {0x2ff7a4: 15, 0x2ff7b8: 16}}
# strings a relocated file keeps at their original offsets (script.build_md pins): mapld 0-16 (location templates
# {var}/{var}, ????, 11 special-region names, 現在地) are read by fixed offsets in the save-slot location line
# (0x406120: li 0x681/0x687, table @0x782de8), EvWindowGroupSymbolName (li 0x690/0x699) and the area banner.
PINS = {'mapldmes': range(17),
        'itemdmes': [1]}             # li 0x1efa in EvMesWinMessPandemonium (0x135944): the carved-numbers message
# (lui file offset, ori file offset, string index): constants whose `lui` sits in another branch's delay slot, so
# imm_pairs (straight-line scan) misses them. Found 2026-11-24 by pairing every unpaired ori with earlier luis and
# tracing the branches by hand: btlmes 4691 'All Foes' showed spell-detail text when targeting all foes.
SHARED_HI = {'btlmes': [(0x116da8, 0x116ddc, 4691), (0x116dbc, 0x116dd4, 4690), (0xe56f0, 0xe570c, 4613),
                        (0xe6484, 0xe64a8, 4532), (0xe6498, 0xe64b8, 4531), (0x160130, 0x160198, 4618)]}


def imm_singles(data, old, first):
    idx = {}
    for i, o in enumerate(old): idx.setdefault(o, i)
    return [[(p, q, kind, idx[v])] for p, q, kind, v in imm_pairs(data) if v in idx and idx[v] >= first]


def patch_imm(binaries, moved, log=None, files=None):
    """Rewrite lui/ori constant runs (imm_runs) holding old offsets of relocated files. Returns {disc path: bytes}."""
    import glob
    files = files or ['work/orig/SLPM_659.52'] + sorted(
        os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, 'work/orig/DLL/**/*.REL'), recursive=True))
    out = {}
    for b in files:
        dp = disc_path(b)
        orig = open(os.path.join(ROOT, b), 'rb').read()
        for name, (old, new) in moved.items():
            runs = imm_runs(orig, old)
            if name in SINGLES and b == 'work/orig/SLPM_659.52':
                done = {h[0] for r in runs for h in r}
                runs += [r for r in imm_singles(orig, old, SINGLES[name]) if r[0][0] not in done]
            for run in runs:
                data = bytearray(out.get(dp, binaries.get(dp, orig)))
                for p, q, kind, i in run:
                    v = new[i]
                    hi = v >> 16 if kind == 'ori' else (v + 0x8000) >> 16
                    lo = v & 0xFFFF if kind == 'ori' else (v - (hi << 16)) & 0xFFFF
                    w, = struct.unpack_from('<I', data, p); x, = struct.unpack_from('<I', data, q)
                    struct.pack_into('<I', data, p, (w & 0xFFFF0000) | hi)
                    struct.pack_into('<I', data, q, (x & 0xFFFF0000) | lo)
                out[dp] = bytes(data)
                if log is not None: log.append(f'patched {name}[{run[0][3]}:{run[-1][3] + 1}] immediates in {dp}@{run[0][0]:#x}')
            if b == 'work/orig/SLPM_659.52':
                for p, i in LI_SITES.get(name, {}).items():
                    data = bytearray(out.get(dp, binaries.get(dp, orig)))
                    w, = struct.unpack_from('<I', data, p)
                    assert w >> 21 == 0x24000000 >> 21 and w & 0xFFFF == old[i], (name, hex(p), hex(w))   # addiu rX, zero
                    assert new[i] < 0x8000, (name, i, hex(new[i]))
                    struct.pack_into('<I', data, p, (w & 0xFFFF0000) | new[i])
                    out[dp] = bytes(data)
                    if log is not None: log.append(f'patched {name}[{i}] li in {dp}@{p:#x}')
                for lp, op, i in SHARED_HI.get(name, []):
                    data = bytearray(out.get(dp, binaries.get(dp, orig)))
                    w, = struct.unpack_from('<I', data, lp); x, = struct.unpack_from('<I', data, op)
                    o0, = struct.unpack_from('<I', orig, lp)
                    assert w >> 26 == 0x0F and x >> 26 == 0x0D, (name, hex(lp), hex(op))        # lui / ori
                    assert (o0 & 0xFFFF) << 16 | x & 0xFFFF == old[i], (name, i, hex(op))
                    # another constant may share this lui: it must already hold the same high half (or be untouched)
                    assert w & 0xFFFF in (o0 & 0xFFFF, new[i] >> 16), (name, i, hex(lp), 'lui shared by two highs')
                    struct.pack_into('<I', data, lp, (w & 0xFFFF0000) | new[i] >> 16)
                    struct.pack_into('<I', data, op, (x & 0xFFFF0000) | new[i] & 0xFFFF)
                    out[dp] = bytes(data)
                    if log is not None: log.append(f'patched {name}[{i}] shared-lui ori in {dp}@{op:#x}')
    return out


def patch(binaries, moved, log=None):
    """binaries: {disc path: bytes} (current content, e.g. ELF with debug patch).
    moved: {message file: (old offsets, new offsets)}. Returns {disc path: new bytes} for changed ones."""
    t = tables(); out = {}
    keep = [(b, i, i + 4 * n) for name, hits in t.items() if name not in moved
            for b, i, k, n, e in hits if e == '<' and i % 4 == 0]
    for name, (old, new) in moved.items():
        for b, i, k, n, e in t.get(name, []):
            if e != '<' or i % 4 or n < 3: continue
            orig = open(os.path.join(ROOT, b), 'rb').read()
            if _arith_continues(orig, i, n):
                if log is not None: log.append(f'skip {name} {b}@{i:#x}: arithmetic sequence'); continue
            if any(kb == b and ks < i + 4 * n and i < ke and (ke - ks) > 4 * n for kb, ks, ke in keep):
                if log is not None: log.append(f'skip {name} {b}@{i:#x}: inside another file\'s table'); continue
            dp = disc_path(b)
            data = bytearray(out.get(dp, binaries.get(dp, orig)))
            for j in range(n):
                cur = struct.unpack_from('<I', data, i + 4 * j)[0]
                assert cur == old[k + j], (name, b, i, j)
                struct.pack_into('<I', data, i + 4 * j, new[k + j])
            out[dp] = bytes(data)
            if log is not None: log.append(f'patched {name}[{k}:{k + n}] in {dp}@{i:#x}')
    return out
