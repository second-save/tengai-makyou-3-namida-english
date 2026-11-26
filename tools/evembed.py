#!/usr/bin/env python3
"""Message files embedded in EVENTARC map modules, and message offsets inside event scripts.

Each town/dungeon map module (`mttc_p`, `mttc_r`, `mnng_p`...) carries its own copy of the map's message file
(evm*mes, 116 of them; the inns' evryokan is not embedded) at the end of the module; header word 2 (offset 8)
is where it starts. NPCs read that copy, not the MESARC one: until 2026-11-22 every villager line stayed in
Japanese (user report; seen in Takachiho, evmttc:49). The build replaces each embedded copy with the rebuilt file.

Event scripts address strings by byte offset. Module layout (Ev_DataEntry @ 0x11b4f8, base = file + 0x10):
int table at base + word[4], float table at base + word[5]; word[7] classes listed at 0x20 as (id, offset of
[n, (method id, code offset) x n]). Bytecode (Ev_Exec @ 0x11bbc0) is u16: op = w & 0x3f, operands are table
indices (bit 15 = float table); 0x1d/0x21 store a table value into a call argument slot, 0x16 calls a script
method. The int table is deduplicated and also holds variables, so one entry can serve a message and a flag.
Files that keep their offsets (script.build_tiled) need nothing more. A relocated file read by events (evmndj,
Dejima: 1,016 strings, too many to tile) gets its offsets rewritten in its owner modules (those whose int table
holds every offset of the file): every int entry with an old offset value takes the new one, except entries
also used for something else than the message call; those strings are pinned at their old offset (pins()).

library: pins(eventarc_path, name, old_offsets) -> {string index: old offset}
         patch(eventarc_path, built, moved) -> (EVENTARC bytes, [log lines])
"""
import collections, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
from cmp import compress, decompress

BASE = 0x10


def embedded(mod):
    """-> (start, length) of the MD file at the end of a decompressed module, or None."""
    if len(mod) < 16: return None
    p = struct.unpack_from('<I', mod, 8)[0]
    if not 16 <= p < len(mod) - 10 or mod[p:p + 2] != b'MD': return None
    return p, len(mod) - p


def length(w):
    """Instruction length in u16 words (Ev_Exec)."""
    op, n = w & 0x3F, (w >> 6) & 0x7F
    if op in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 0x22, 0x23): return 3
    if op in (6, 7, 0xF, 0x16, 0x18): return 2
    if 0x10 <= op <= 0x15 or op in (0x24, 0x25): return 4
    if op in (0x17, 0x1B, 0x1E, 0x1F, 0x26): return 1
    if op in (0x19, 0x1A): return 1 + n
    if op in (0x1C, 0x1D, 0x20, 0x21): return 3 if w & 0x4000 else 2
    if op == 0x27: return 5 if n == 0 else 1
    raise ValueError(f'unknown event op {w:#06x}')


def int_table(mod):
    u32 = lambda o: struct.unpack_from('<I', mod, o)[0]
    a, b = BASE + u32(0x10), BASE + u32(0x14)
    return a, list(struct.unpack_from(f'<{(b - a) // 4}I', mod, a))


def instructions(mod):
    """Yield (pos, word, operand words) for every method of the module, decoded from its start to the next."""
    u32 = lambda o: struct.unpack_from('<I', mod, o)[0]
    codes = sorted({u32(BASE + u32(0x24 + 8 * k) + 8 + 8 * j)
                    for k in range(u32(0x1C)) for j in range(u32(BASE + u32(0x24 + 8 * k)))})
    for a, b in zip(codes, codes[1:] + [None]):
        q, stop = BASE + a, BASE + b if b else len(mod)
        while q < stop:
            w = struct.unpack_from('<H', mod, q)[0]; n = length(w)
            yield q, w, struct.unpack_from(f'<{n - 1}H', mod, q + 2)
            q += 2 * n
            if b is None and w & 0x3F == 0x17: break
        assert b is None or q == stop, f'method at {a:#x} does not decode to the next one'


def int_refs(w, o):
    """Int-table indices an instruction reads or writes, as (index, kind); kind 'arg' = stored to a call slot."""
    op, n = w & 0x3F, (w >> 6) & 0x7F
    if op in (0x1D, 0x21): refs = [(o[0], 'arg')] + ([(o[1], 'other')] if w & 0x4000 else [])
    elif op == 1: refs = [(o[0], 'other'), (o[1], 'copy')]
    elif op in (2, 3, 4, 5): refs = [(n | (w & 0x8000), 'other'), (o[0], 'other'), (o[1], 'other')]
    elif 6 <= op <= 0xE or op == 0x22: refs = [(n, 'other')] + [(x & 0x7FFF, 'other') for x in o[:2]]
    elif 0x10 <= op <= 0x15: refs = [(o[0], 'other'), (o[1], 'other')]
    elif op in (0x19, 0x1A): refs = [(x, 'other') for x in o]
    elif op in (0x1C, 0x20): refs = [(o[0], 'other')] + ([(o[1], 'other')] if w & 0x4000 else [])
    elif op == 0x23: refs = [(o[0], 'other')]
    elif op in (0x24, 0x25): refs = [(o[0], 'other'), (o[1], 'other')]
    elif op == 0x27 and n == 0: refs = [(o[2], 'other')]
    else: refs = []
    return [(x, k) for x, k in refs if x != 0xFFFF and not x & 0x8000]


def analyse(mod, old):
    """old: set of a message file's offsets. -> (message method, {int index: set of uses}) where a use is
    'msg' (argument of the message method), 'copy' (copied to a variable) or 'other'."""
    _, vals = int_table(mod)
    uses = collections.defaultdict(set); calls = collections.Counter(); pending = []
    for q, w, o in instructions(mod):
        op = w & 0x3F
        for x, kind in int_refs(w, o):
            if kind == 'arg': pending.append(x)
            else: uses[x].add(kind)
        if op in (0x16, 0x18):
            for x in pending: uses[x].add((op, o[0]))
            if op == 0x16: calls.update((o[0],) for x in pending if vals[x] in old)
            pending = []
        elif op in (0x17, 0xF): pending = []
    method = calls.most_common(1)[0][0][0]
    out = {}
    for i, v in enumerate(vals):
        if v in old:
            out[i] = {'msg' if u == (0x16, method) else u if u in ('copy', 'other') else 'other' for u in uses[i]}
    return method, out


_CACHE = {}


def _modules(path):
    if path not in _CACHE:
        a = afs.Afs(path); out = []
        for i in range(len(a.ents)):
            data = a.data(i)
            out.append((i, a.names[i], data, decompress(data) if data[:4] == b'CMP\0' else None))
        _CACHE[path] = out
    return _CACHE[path]


def owners(path, old):
    """Modules whose int table holds every offset of the file (others only hold coincidences, < 10%)."""
    old = set(old)
    return [n for _, n, _, mod in _modules(path) if mod and len(mod) > 0x40
            and old <= set(int_table(mod)[1])]


def pins(path, name, old_offsets):
    """{string index: old offset} for strings whose offset constant is also used outside the message call."""
    old = set(old_offsets); keep = set()
    for _, n, _, mod in _modules(path):
        if not mod or len(mod) <= 0x40 or not old <= set(int_table(mod)[1]): continue
        _, vals = int_table(mod)
        for i, u in analyse(mod, old)[1].items():
            if 'other' in u or (u - {'msg', 'copy'}): keep.add(vals[i])
    return {k: o for k, o in enumerate(old_offsets) if o in keep}


def patch(path, built, moved):
    """built: {message file: (original raw, new raw)}; moved: {name: (old offsets, new offsets)} relocated files:
    their owner modules get the new offsets (pinned strings kept theirs) and their embedded copy."""
    by_raw = {orig: name for name, (orig, new) in built.items() if orig != new}
    oldsets = {name: set(old) for name, (old, new) in moved.items()}
    members, log = [], []
    a = afs.Afs(path)
    for i, n, data, mod in _modules(path):
        if mod and len(mod) > 0x40:
            changed = False
            ivals = int_table(mod)
            for name, old in oldsets.items():
                if not old <= set(ivals[1]): continue           # not an owner of this relocated file
                omap = dict(zip(*moved[name]))
                _, uses = analyse(mod, old)
                mod = bytearray(mod); at = ivals[0]; nre = 0
                for k, u in uses.items():
                    v = ivals[1][k]
                    if u <= {'msg', 'copy'} and omap[v] != v:
                        struct.pack_into('<I', mod, at + 4 * k, omap[v]); nre += 1
                    else:
                        assert omap[v] == v, f'{n}: int entry {k} ({v}) is shared but its string moved'
                mod = bytes(mod); changed = True
                log.append(f'{name}: {nre} offsets rewritten in {n}')
            e = embedded(mod)
            if e:
                p, sz = e
                name = next((nm for orig, nm in by_raw.items() if len(orig) <= sz < len(orig) + 4
                             and mod[p:p + len(orig)] == orig), None)
                if name:
                    new = built[name][1]
                    mod = mod[:p] + new + b'\0' * (-len(new) % 4); changed = True
                    log.append(f'{name} -> {n} ({sz} -> {len(new)} bytes)')
            if changed: data = compress(mod)
        members.append(data)
    return afs.build(members, [a.meta(i) for i in range(len(a.ents))]), log
