#!/usr/bin/env python3
"""Sprite rectangles of RenderWare window models (clumps in .crp2 members): which part of a texture each quad shows.

Window graphics (WINARC/SGARC `wsg99_*`, `wcm*`...) are clumps of small flat geometries; each geometry's texture
coordinates select a piece of an atlas texture. Words split across an atlas (SGARC 終/了, 攻略時/間) are drawn as
several such pieces, so English replacing them must respect these rectangles.

usage: rwgeo.py ARCHIVE MEMBER [TEXREGEX]   -> one line per geometry: texture, UV rect in texels, vertex bbox
library: pieces(raw_member) -> [dict(tex, uv=(u0, v0, u1, v1) in 0..1, xy=(x0, y0, x1, y1), clump, geo)]
"""
import os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs, txd
from cmp import decompress

CONTAINERS = {0x10, 0x1A, 0x0F, 0x08, 0x07, 0x06, 0x03, 0x0E, 0x14, 0x16}


def _chunks(d, o, end):
    while o + 12 <= end:
        t, sz, ver = struct.unpack_from('<III', d, o)
        if sz > end - o - 12: return
        yield t, o + 12, sz
        o += 12 + sz


def _geometry(d, p, sz):
    """Geometry chunk body -> (uvs, verts, [texture names of its materials])."""
    st = next(((q, s) for t, q, s in _chunks(d, p, p + sz) if t == 1), None)
    q = st[0]
    flags, nsets, native, ntri, nv, nmorph = struct.unpack_from('<HBBIII', d, q); q += 16
    if native: return None
    if flags & 8: q += 4 * nv                                  # prelit colours
    nsets = nsets or (1 if flags & 4 else 0) + (1 if flags & 0x80 else 0)
    uvs = [struct.unpack_from('<ff', d, q + 8 * k) for k in range(nv)] if nsets else []
    q += 8 * nv * nsets
    tris = [struct.unpack_from('<HHHH', d, q + 8 * k) for k in range(ntri)]   # v2, v1, material, v3 (RW order)
    q += 8 * ntri + 16                                         # triangles, bounding sphere
    hasv, hasn = struct.unpack_from('<II', d, q); q += 8
    verts = [struct.unpack_from('<fff', d, q + 12 * k) for k in range(nv)] if hasv else []
    names = []
    for t, mp, ms in _chunks(d, p, p + sz):
        if t == 8:
            for t2, p2, s2 in _chunks(d, mp, mp + ms):
                if t2 == 7:
                    tex = next(((p3, s3) for t3, p3, s3 in _chunks(d, p2, p2 + s2) if t3 == 6), None)
                    if tex:
                        s = next((d[p4:p4 + s4].split(b'\0')[0].decode('latin1') for t4, p4, s4 in
                                  _chunks(d, tex[0], tex[0] + tex[1]) if t4 == 2), '')
                        names.append(s)
    return uvs, verts, names, tris


def pieces(raw):
    d = decompress(raw) if raw[:3] == b'CMP' else raw
    out = []; o = 0; clump = 0
    while o + 12 <= len(d):
        t, sz, ver = struct.unpack_from('<III', d, o)
        if o + 12 + sz > len(d): break
        if t == 0x10:
            clump += 1; g = 0
            for t2, p2, s2 in _chunks(d, o + 12, o + 12 + sz):
                if t2 != 0x1A: continue
                for t3, p3, s3 in _chunks(d, p2, p2 + s2):
                    if t3 != 0x0F: continue
                    r = _geometry(d, p3, s3); g += 1
                    if not r or not r[0]: continue
                    uvs, verts, names, tris = r
                    us, vs = [u for u, v in uvs], [v for u, v in uvs]
                    xs, ys = [x for x, y, z in verts] or [0], [y for x, y, z in verts] or [0]
                    out.append(dict(tex=names[0] if names else '?', uv=(min(us), min(vs), max(us), max(vs)),
                                    xy=(min(xs), min(ys), max(xs), max(ys)), clump=clump, geo=g, nv=len(uvs),
                                    uvs=uvs, verts=[(x, y) for x, y, z in verts],
                                    tris=[(a, b, c) for b, a, m, c in tris]))
        o += 12 + sz
    return out


def move(d, clump, geo, dx, dy, tex=None, uv=None):
    """Shift geometry `geo` (1-based, as pieces() numbers it) of clump `clump` by (dx, dy) model units, in place
    (d: decompressed bytearray). Vertices and bounding sphere move; nothing else changes size.
    With tex + uv (u0, v0, u1, v1 in 0..1): only the quad(s) drawn with that texture inside that UV box move (one
    label inside a multi-texture panel). Vertices they share with other triangles are duplicated first (d grows)."""
    o = 0; c = 0
    while o + 12 <= len(d):
        t, sz, ver = struct.unpack_from('<III', d, o)
        if t == 0x10:
            c += 1
            if c == clump:
                gs = [(p3, s3, p2) for t2, p2, s2 in _chunks(d, o + 12, o + 12 + sz) if t2 == 0x1A
                      for t3, p3, s3 in _chunks(d, p2, p2 + s2) if t3 == 0x0F]
                p, s, pl = gs[geo - 1]
                sel = None
                if uv:
                    uvs, _, names, tris = _geometry(d, p, s)
                    inside = lambda k: uv[0] - 1e-4 <= uvs[k][0] <= uv[2] + 1e-4 and uv[1] - 1e-4 <= uvs[k][1] <= uv[3] + 1e-4
                    mine = [t for t in tris if names[t[2]] == tex and all(inside(k) for k in (t[0], t[1], t[3]))]
                    sel = {k for t in mine for k in (t[0], t[1], t[3])}
                    assert sel, (clump, geo, tex, uv)
                    shared = sorted({k for t in tris if t not in mine for k in (t[0], t[1], t[3])} & sel)
                    if shared:
                        _unshare(d, o, pl, p, s, mine, shared)
                        return move(d, clump, geo, dx, dy, tex, uv)
                q = next(q for t, q, s_ in _chunks(d, p, p + s) if t == 1)
                flags, nsets, native, ntri, nv, nmorph = struct.unpack_from('<HBBIII', d, q); q += 16
                assert not native
                if flags & 8: q += 4 * nv
                nsets = nsets or (1 if flags & 4 else 0) + (1 if flags & 0x80 else 0)
                q += 8 * nv * nsets + 8 * ntri
                if sel is None:                               # a part moving leaves the panel's sphere as it is
                    sx, sy = struct.unpack_from('<ff', d, q); struct.pack_into('<ff', d, q, sx + dx, sy + dy)
                q += 16
                hasv, hasn = struct.unpack_from('<II', d, q); q += 8
                assert hasv
                for k in (range(nv) if sel is None else sorted(sel)):
                    x, y = struct.unpack_from('<ff', d, q + 12 * k); struct.pack_into('<ff', d, q + 12 * k, x + dx, y + dy)
                return
        o += 12 + sz
    raise KeyError(f'no clump {clump}')


def _unshare(d, oc, pl, p, s, mine, shared):
    """Give the triangles `mine` their own copies of the vertices `shared` (appended at the end of the vertex arrays);
    their triangle and BinMesh (0x50e, triangle lists) indices follow. Clump, geometry list, geometry and struct
    chunk sizes grow."""
    q0 = next(q for t, q, s_ in _chunks(d, p, p + s) if t == 1)
    flags, nsets, native, ntri, nv, nmorph = struct.unpack_from('<HBBIII', d, q0)
    assert not native and nmorph == 1 and not flags & 8 and (nsets or 1) == 1 and not flags & 1, hex(flags)
    new = {k: nv + i for i, k in enumerate(shared)}
    keys = {frozenset((t[0], t[1], t[3])) for t in mine}
    uvp = q0 + 16; tp = uvp + 8 * nv; vp = tp + 8 * ntri + 16
    hasv, hasn = struct.unpack_from('<II', d, vp); vp += 8
    for i in range(ntri):                                       # (v2, v1, material, v3), as _geometry reads them
        a, b, m, c = struct.unpack_from('<HHHH', d, tp + 8 * i)
        if frozenset((a, b, c)) in keys:
            struct.pack_into('<HHHH', d, tp + 8 * i, new.get(a, a), new.get(b, b), m, new.get(c, c))
    ext, es = next((q, s_) for t, q, s_ in _chunks(d, p, p + s) if t == 3)
    bm = next(q for t, q, s_ in _chunks(d, ext, ext + es) if t == 0x50E)
    bflags, nmesh, _ = struct.unpack_from('<III', d, bm); assert bflags == 0, 'BinMesh tristrip'
    r = bm + 12
    for _ in range(nmesh):
        n, mat = struct.unpack_from('<II', d, r); r += 8
        for i in range(0, n, 3):
            ix = struct.unpack_from('<III', d, r + 4 * i)
            if frozenset(ix) in keys: struct.pack_into('<III', d, r + 4 * i, *(new.get(k, k) for k in ix))
        r += 4 * n
    nrm = vp + 12 * nv                                          # insert from the back so earlier offsets hold
    if hasn: d[nrm + 12 * nv:nrm + 12 * nv] = b''.join(d[nrm + 12 * k:nrm + 12 * k + 12] for k in shared)
    d[vp + 12 * nv:vp + 12 * nv] = b''.join(d[vp + 12 * k:vp + 12 * k + 12] for k in shared)
    d[tp:tp] = b''.join(d[uvp + 8 * k:uvp + 8 * k + 8] for k in shared)
    struct.pack_into('<I', d, q0 + 8, nv + len(shared))
    grow = len(shared) * (8 + 12 + (12 if hasn else 0))
    for hdr in (q0 - 12, p - 12, pl - 12, oc):                  # struct, geometry, geometry list, clump
        struct.pack_into('<I', d, hdr + 4, struct.unpack_from('<I', d, hdr + 4)[0] + grow)


def quads(p, size):
    """Axis-aligned pieces of one geometry: triangles grouped by identical UV bbox ->
    [(texel rect (x0, y0, x1, y1), screen rect (x0, y0, x1, y1) y up)], in triangle order."""
    w, h = size; out = []
    for a, b, c in p['tris']:
        uv = [p['uvs'][i] for i in (a, b, c)]; xy = [p['verts'][i] for i in (a, b, c)]
        t = (round(min(u for u, v in uv) * w), round(min(v for u, v in uv) * h),
             round(max(u for u, v in uv) * w), round(max(v for u, v in uv) * h))
        s = (min(x for x, y in xy), min(y for x, y in xy), max(x for x, y in xy), max(y for x, y in xy))
        if out and out[-1][0] == t:
            o = out[-1][1]; out[-1] = (t, (min(o[0], s[0]), min(o[1], s[1]), max(o[2], s[2]), max(o[3], s[3])))
        elif t[2] > t[0] and t[3] > t[1]: out.append((t, s))
    seen = []; [seen.append(q) for q in out if q[0] not in [x[0] for x in seen]]
    return seen


def _bary(px, py, a, b, c):
    import numpy as np
    (x1, y1), (x2, y2), (x3, y3) = a, b, c
    den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(den) < 1e-9: return None
    l1 = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / den
    l2 = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / den
    return l1, l2, 1 - l1 - l2


def screen_map(ps, tex, size, scale=1.0):
    """Texel -> screen correspondence for geometries ps (pieces() dicts) drawing texture `tex` of size (w, h).
    -> (mask (h, w) bool, sx (h, w), sy (h, w)): screen position (y down, origin at the pieces' top-left, in
    model units * scale) of every texel some triangle covers."""
    import numpy as np
    w, h = size
    mask = np.zeros((h, w), bool); sx = np.zeros((h, w)); sy = np.zeros((h, w))
    ty, tx = np.mgrid[0:h, 0:w] + 0.5
    allx = [x for p in ps for x, y in p['verts']]; ally = [y for p in ps for x, y in p['verts']]
    ox, oy = min(allx), max(ally)
    for p in ps:
        if p['tex'] != tex: continue
        uv = [(u * w, v * h) for u, v in p['uvs']]
        for a, b, c in p['tris']:
            r = _bary(tx, ty, uv[a], uv[b], uv[c])
            if r is None: continue
            l1, l2, l3 = r
            inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
            for arr, k in ((sx, 0), (sy, 1)):
                va, vb, vc = p['verts'][a][k], p['verts'][b][k], p['verts'][c][k]
                val = l1 * va + l2 * vb + l3 * vc
                arr[inside] = ((val - ox) if k == 0 else (oy - val))[inside] * scale
            mask |= inside
    return mask, sx, sy


def texel_screen(ps, size, layout=None):
    """-> (mask, sx, sy): for every texel of a (w, h) texture drawn by geometries ps, its screen position in model
    units (y up), first triangle wins. layout='row': pieces are placed left to right in list order (banners whose
    glyph pieces are each centred at 0 and laid out by code)."""
    import numpy as np
    w, h = size
    mask = np.zeros((h, w), bool); sx = np.zeros((h, w)); sy = np.zeros((h, w))
    ty, tx = np.mgrid[0:h, 0:w] + 0.5
    cursor = 0.0
    for p in ps:
        verts = p['verts']
        if layout == 'row':
            x0 = min(x for x, y in verts); cy = (min(y for x, y in verts) + max(y for x, y in verts)) / 2
            verts = [(x - x0 + cursor, y - cy) for x, y in verts]; cursor = max(x for x, y in verts)
        uv = [(u * w, v * h) for u, v in p['uvs']]
        for a, b, c in p['tris']:
            r = _bary(tx, ty, uv[a], uv[b], uv[c])
            if r is None: continue
            l1, l2, l3 = r
            inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6) & ~mask
            sx[inside] = (l1 * verts[a][0] + l2 * verts[b][0] + l3 * verts[c][0])[inside]
            sy[inside] = (l1 * verts[a][1] + l2 * verts[b][1] + l3 * verts[c][1])[inside]
            mask |= inside
    return mask, sx, sy


def render(ps, texs, scale=1.0):
    """Draw geometries as the game would (flat, y up -> down): -> RGBA image. texs: {name: (H, W, 4) array}."""
    import numpy as np
    from PIL import Image
    allx = [x for p in ps for x, y in p['verts']]; ally = [y for p in ps for x, y in p['verts']]
    W, H = int((max(allx) - min(allx)) * scale) + 1, int((max(ally) - min(ally)) * scale) + 1
    out = np.zeros((H, W, 4), np.uint8)
    for p in ps:
        img = texs.get(p['tex'])
        if img is None: continue
        th, tw = img.shape[:2]
        mask, sx, sy = screen_map([p], p['tex'], (tw, th), scale)
        ys, xs = np.nonzero(mask)
        X = np.clip(sx[ys, xs].astype(int), 0, W - 1); Y = np.clip(sy[ys, xs].astype(int), 0, H - 1)
        # shift: screen_map's origin is the piece's own top-left; place it in the clump frame
        px0 = (min(x for x, y in p['verts']) - min(allx)) * scale; py0 = (max(ally) - max(y for x, y in p['verts'])) * scale
        X = np.clip((X + px0).astype(int), 0, W - 1); Y = np.clip((Y + py0).astype(int), 0, H - 1)
        out[Y, X] = img[ys, xs]
    return Image.fromarray(out, 'RGBA')


if __name__ == '__main__':
    arc, mem = sys.argv[1], sys.argv[2]; rx = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
    a = afs.Afs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'work', 'orig', arc + '.AFS'))
    raw = a.data(a.index(mem))
    sizes = {t['name']: t['img'].shape[1::-1] for t in txd.textures(raw) if t.get('img') is not None}
    for p in pieces(raw):
        if rx and not rx.search(p['tex']): continue
        w, h = sizes.get(p['tex'], (1, 1))
        u0, v0, u1, v1 = p['uv']; x0, y0, x1, y1 = p['xy']
        print(f"clump {p['clump']:3d} geo {p['geo']:2d} {p['tex']:16s} texels ({u0 * w:6.1f},{v0 * h:6.1f})-({u1 * w:6.1f},{v1 * h:6.1f})"
              f"  of {w}x{h}  xy ({x0:7.1f},{y0:7.1f})-({x1:7.1f},{y1:7.1f})  verts {p['nv']}")
        if '--quads' in sys.argv and p['nv'] > 4:
            for t, s in quads(p, (w, h)):
                print(f"      quad texels {t}  screen ({s[0]:.0f},{s[1]:.0f})-({s[2]:.0f},{s[3]:.0f})")
