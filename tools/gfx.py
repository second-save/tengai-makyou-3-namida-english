#!/usr/bin/env python3
"""Text graphics: draw English over Japanese labels in WINARC textures and re-insert them (inverse of txd.py).

Edits live in gfx/labels.json: a list of
  {"member": "cm.crp2", "tex": "wcm99_300", "box": [x0, y0, x1, y1], "text": "Items",
   "bg": "clear" | "solid" | "tile X0 X1" | "keep",          (default "clear")
   "align": "center" | "left" | "right", "size": px (default: largest that fits), "vertical": false,
   "fill": [r, g, b], "edge": [r, g, b], "stroke": 2, "font": "bold" | "regular", "rotate": 90, "note": "..."}
"palette": 16 x [r, g, b, a 0..128] replaces a 4 bpp texture's palette (any one label of the texture carries it).
"opaque": true makes the box fully opaque after bg (tiling from a strip's faded, text-free end).
rotate 90: the label is stored turned 90 degrees clockwise (reads top to bottom); the text is drawn turned the same way.
box is in texture pixels, x1/y1 exclusive. bg: "clear" makes the box transparent, "solid" fills it with the box's
most common colour, "tile X0 X1" repeats columns X0..X1 of the same rows across the box (text-free strip of the same
wood/parchment; "tile X0 X1 Y0" takes them from rows starting at Y0, e.g. a text-free plate of the same kind), "keep" draws over what is there. fill/edge default to the box's own light and dark ink.
New pixels are mapped to the texture's own palette, so palettes and all other bytes stay as they were.

    gfx.py preview OUTDIR [REGEX]   edited textures as PNG (decoded back from what was written), plus a 4x zoom
"archive": "BTLARC" | "EFFARC" for textures outside WINARC (default).
library: build_all(od) -> {disc path: AFS bytes} with every edit applied (build.py); build_archive(od, arc)
"""
import json, os, re, struct, sys
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs, txd
from cmp import compress, decompress

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = {'bold': os.path.join(ROOT, 'fonts', 'PT_Serif-Web-Bold.ttf'),
         'regular': os.path.join(ROOT, 'fonts', 'PT_Serif-Web-Regular.ttf')}
LABELS = os.path.join(ROOT, 'gfx', 'labels.json')


# ---- writing pixels back -------------------------------------------------------------------------------------------

def _native(raw, texname):
    for p, sz in txd.find_native(raw):
        it = list(txd.chunks(raw, p, p + sz))
        name = raw[it[1][1]:it[1][1] + it[1][2]].split(b'\0')[0].decode('latin1')
        if name != texname: continue
        inner = list(txd.chunks(raw, it[3][1], it[3][1] + it[3][2]))
        return inner[1][1], raw[inner[0][1]:inner[0][1] + inner[0][2]]
    raise KeyError(texname)


def _nearest(rgba, pal):
    """(N, 4) image pixels -> indices of the nearest palette entries (alpha in decoded 0..255 scale)."""
    pl = pal.astype(np.int32); pl[:, 3] = np.minimum(255, pl[:, 3] * 2)
    px = rgba.reshape(-1, 4).astype(np.int32)
    out = np.empty(len(px), np.uint8)
    for s in range(0, len(px), 8192):
        d = px[s:s + 8192, None, :] - pl[None, :, :]
        a = (px[s:s + 8192, None, 3:4] + pl[None, :, 3:4]) / 510.0
        out[s:s + 8192] = ((d[..., :3] ** 2 * a).sum(-1) + 4 * d[..., 3] ** 2).argmin(1)
    return out


def put(raw, texname, rgba, palette=None):
    """Write an (H, W, 4) uint8 image (alpha 0..255, as txd decodes it) into texture texname of raw (bytearray).
    palette: 16 [r, g, b, a] (a in GS scale 0..128) replacing a 4 bpp texture's own palette (label key "palette":
    e.g. wcm99_502 has one brown at 16 alphas, no room for a light outline)."""
    data_off, info = _native(raw, texname)
    w, h, depth, rfmt = struct.unpack_from('<IIII', info, 0)
    psize, palsize = struct.unpack_from('<II', info, 0x30)
    assert rgba.shape[:2] == (h, w), (texname, rgba.shape)
    hdr = 80 if rfmt & 0x20000 else 0
    tw, th = struct.unpack_from('<II', raw, data_off + 0x20) if hdr else (w, h)
    pix = data_off + hdr
    pal_off = data_off + psize + hdr
    if depth == 8:
        pal = np.frombuffer(bytes(raw[pal_off:pal_off + 1024]), np.uint8).reshape(-1, 4)[txd._csm1(256)]
        idx = _nearest(rgba, pal).reshape(h, w)
        if hdr and (tw, th) != (w, h):
            y, x = np.mgrid[0:h, 0:w]                        # same address map as txd._unswizzle8
            block = (y & ~0xF) * w + (x & ~0xF) * 2
            swap = (((y + 2) >> 2) & 1) * 4
            posy = (((y & ~3) >> 1) + (y & 1)) & 7
            col = posy * w * 2 + ((x + swap) & 7) * 4
            byte = ((y >> 1) & 1) + ((x >> 2) & 2)
            buf = np.frombuffer(bytes(raw[pix:pix + w * h]), np.uint8).copy()
            buf[(block + col + byte).reshape(-1)] = idx.reshape(-1)
            raw[pix:pix + w * h] = buf.tobytes()
        else:
            raw[pix:pix + w * h] = idx.tobytes()
    elif depth == 4:
        if palette is not None:
            assert len(palette) == 16, texname
            raw[pal_off:pal_off + 64] = bytes(v for c in palette for v in c)
        pal = np.frombuffer(bytes(raw[pal_off:pal_off + 64]), np.uint8).reshape(-1, 4)
        idx = _nearest(rgba, pal).reshape(h, w)
        n = w * h // 2
        if hdr and (tw, th) != (w, h):
            a4 = txd._a4(w, h).reshape(-1)
            if tw * th * 2 == n:                             # PSMCT16 upload: halfword memory
                addr = txd._addr16(tw, th).reshape(-1)
                old = np.frombuffer(bytes(raw[pix:pix + n]), '<u2')
                mem = np.zeros(int(max(addr.max(), a4.max() // 4)) + 4096, '<u2'); mem[addr] = old
                nib = np.empty(mem.size * 4, np.uint8)
                for k in range(4): nib[k::4] = (mem >> (4 * k)) & 15
                nib[a4] = idx.reshape(-1)
                mem = sum(nib[k::4].astype('<u2') << (4 * k) for k in range(4)).astype('<u2')
                raw[pix:pix + n] = mem[addr].tobytes()
            elif tw * th * 4 == n:                           # PSMCT32 upload: word memory
                bt32, ct32 = np.array(txd.BT32), np.array(txd.CT32)
                dbw = max(1, tw // 64)
                y, x = np.mgrid[0:th, 0:tw]
                addr = (((y // 32) * dbw + x // 64) * 2048 + bt32[(y % 32) // 8, (x % 64) // 8] * 64
                        + ct32[y % 8, x % 8]).reshape(-1)
                old = np.frombuffer(bytes(raw[pix:pix + n]), '<u4')
                mem = np.zeros(int(max(addr.max(), a4.max() // 8)) + 2048, '<u4'); mem[addr] = old
                nib = np.empty(mem.size * 8, np.uint8)
                for k in range(8): nib[k::8] = (mem >> (4 * k)) & 15
                nib[a4] = idx.reshape(-1)
                mem = sum(nib[k::8].astype('<u4') << (4 * k) for k in range(8)).astype('<u4')
                raw[pix:pix + n] = mem[addr].tobytes()
            else:
                raise ValueError(f'{texname}: 4 bpp upload {tw}x{th}')
        else:
            flat = idx.reshape(-1)
            raw[pix:pix + n] = (flat[0::2] | (flat[1::2] << 4)).astype(np.uint8).tobytes()
    elif depth == 32 and not (hdr and (tw, th) != (w, h)):
        out = rgba.astype(np.uint16); out[..., 3] = (out[..., 3] + 1) // 2    # GS alpha 0..0x80
        raw[pix:pix + w * h * 4] = out.astype(np.uint8).tobytes()
    else:
        raise ValueError(f'{texname}: depth {depth}')


# ---- drawing -------------------------------------------------------------------------------------------------------

def _inks(region):
    """(fill, edge) of the original lettering: fill = median colour inside the strokes (opaque pixels whose four
    neighbours are opaque too), edge = median of the opaque pixels on the stroke border."""
    op = region[..., 3] > 200
    inner = op.copy()
    inner[1:] &= op[:-1]; inner[:-1] &= op[1:]; inner[:, 1:] &= op[:, :-1]; inner[:, :-1] &= op[:, 1:]
    rim = (region[..., 3] > 100) & ~inner
    if inner.sum() < 8 or rim.sum() < 8: return (255, 251, 226), (100, 66, 35)
    return (tuple(np.median(region[inner][:, :3], 0).astype(int)), tuple(np.median(region[rim][:, :3], 0).astype(int)))


def _background(img, box, mode):
    x0, y0, x1, y1 = box
    if mode == 'keep': return
    if mode == 'clear': img[y0:y1, x0:x1] = 0; return
    if mode == 'solid':
        c = Counter(map(tuple, img[y0:y1, x0:x1].reshape(-1, 4))).most_common(1)[0][0]
        img[y0:y1, x0:x1] = c; return
    if m := re.fullmatch(r'solid (\d+) (\d+) (\d+)', mode):     # a given colour over the shape's interior (keeps
        op = img[y0:y1, x0:x1, 3] > 0                             # a 2 px rim, e.g. an icon's outline)
        inner = op.copy()
        for _ in range(2):
            e = inner.copy(); e[1:] &= inner[:-1]; e[:-1] &= inner[1:]; e[:, 1:] &= inner[:, :-1]; e[:, :-1] &= inner[:, 1:]
            inner = e
        img[y0:y1, x0:x1][inner] = [*map(int, m.groups()), 255]; return
    if mode.startswith(('disc ', 'poly ')):                  # fill a circle (cx cy r) or polygon (x y x y ...) with
        nums = [float(v) for v in mode.split()[1:]]           # the most common colour inside it (round/diamond emblems)
        given = None                                          # disc cx cy r [R G B]: a given colour instead
        if mode.startswith('disc') and len(nums) == 6: given = (*map(int, nums[3:]), 255); nums = nums[:3]
        lay = Image.new('L', (img.shape[1], img.shape[0]), 0); d = ImageDraw.Draw(lay)
        if mode.startswith('disc'):
            cx, cy, r = nums; d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        else: d.polygon(list(zip(nums[0::2], nums[1::2])), fill=255)
        sel = np.array(lay) > 127
        c = given or Counter(map(tuple, img[sel].reshape(-1, 4))).most_common(1)[0][0]
        img[sel] = c; return
    m = re.fullmatch(r'tile (\d+) (\d+)(?: (\d+))?', mode)   # optional 3rd number: source rows start there instead
    if not m: raise ValueError(f'bg {mode!r}')
    a, b = int(m.group(1)), int(m.group(2))
    sy = int(m.group(3)) if m.group(3) else y0
    strip = img[sy:sy + y1 - y0, a:b].copy()
    for x in range(x0, x1): img[y0:y1, x] = strip[:, (x - x0) % (b - a)]


def draw_label(img, e):
    if 'art' in e:                                  # scale the whole picture into this rect first (makes room for a
        ax0, ay0, ax1, ay1 = e['art']               # subtitle, e.g. the staff-roll calligraphy, decision D5)
        small = np.array(Image.fromarray(img).resize((ax1 - ax0, ay1 - ay0), Image.LANCZOS))
        img[:] = 0; img[ay0:ay1, ax0:ax1] = small
    x0, y0, x1, y1 = e['box']
    light, dark = _inks(img[y0:y1, x0:x1])
    ys, xs = np.nonzero(img[y0:y1, x0:x1, 3] > 100)                 # the original lettering's extent
    ink = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else (0, 0, x1 - x0, y1 - y0)
    fill, edge = tuple(e.get('fill', light)) + (255,), tuple(e.get('edge', dark)) + (255,)
    stroke = e.get('stroke', 2 if (y1 - y0) >= 18 else 1)
    _background(img, e['box'], e.get('bg', 'clear'))
    if e.get('opaque'): img[y0:y1, x0:x1, 3] = 255  # tile source was a faded end of an opaque strip: keep its colour only
    bw, bh = x1 - x0, y1 - y0
    rot = e.get('rotate', 0)                       # 90: text stored turned clockwise (the game turns the sprite back)
    if rot % 180: bw, bh = bh, bw
    font_path = FONTS[e.get('font', 'bold')]
    text = '\n'.join(e['text']) if e.get('vertical') else e['text']
    probe = ImageDraw.Draw(Image.new('RGBA', (1, 1)))

    def bbox(sz):
        f = ImageFont.truetype(font_path, sz)
        return f, probe.multiline_textbbox((0, 0), text, font=f, stroke_width=stroke, spacing=0, align='center')
    size = e.get('size')
    lim_h = bh - 1 if rot or e.get('vertical') or e.get('bg', 'clear') not in ('clear', 'keep') else min(bh - 1, ink[3] - ink[1] + 2)
    if not size:                                   # largest size that fits the box and isn't taller than the original
        size = 6
        while size < 64:
            l, t, r, b = bbox(size + 1)[1]
            if r - l > bw - 2 or b - t > lim_h: break
            size += 1
    f, (l, t, r, b) = bbox(size)
    al = e.get('align', 'center')
    cx = (ink[0] + ink[2]) // 2 if e.get('bg', 'clear') == 'clear' and not e.get('vertical') and not rot else bw // 2
    left = min(max(1, cx - (r - l) // 2), bw - 1 - (r - l))     # centred on the old text, kept inside the box
    px = {'left': 1 - l, 'right': bw - 1 - r}.get(al, left - l)
    cy = (ink[1] + ink[3]) // 2 if e.get('bg', 'clear') == 'clear' and not rot else bh // 2
    py = min(max(0, cy - (b - t) // 2), bh - (b - t)) - t
    layer = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(layer).multiline_text((px, py), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=edge,
                                         spacing=0, align='center')
    if rot: layer = layer.rotate(-rot, expand=True)
    lay = np.array(layer).astype(np.float32) / 255
    base = img[y0:y1, x0:x1].astype(np.float32) / 255
    a = lay[..., 3:4]
    out = lay[..., :3] * a + base[..., :3] * (1 - a)
    alpha = a[..., 0] + base[..., 3] * (1 - a[..., 0])
    img[y0:y1, x0:x1] = np.dstack([out, alpha]).clip(0, 1) * 255


def draw_sigil(imgs, e):
    """Spell sigils (D25): {"sigil": [tex, ...] top to bottom, "text": "Flame"}. The textures, stacked in a column
    (same width), get the English word turned 90 degrees clockwise down the whole column, split back per texture.
    Each texture keeps its own look: core and halo colours sampled from its old glyph; a layer that was only a soft
    glow (no bright core) gets a blurred word. imgs: {tex: (H, W, 4) uint8}, edited in place."""
    from PIL import ImageFilter
    names = e['sigil']; w = imgs[names[0]].shape[1]
    hs = [imgs[n].shape[0] for n in names]; total = sum(hs)
    font = FONTS[e.get('font', 'bold')]
    size = 8                                               # word length runs down the column, letter height across it
    while size < 80:
        f = ImageFont.truetype(font, size + 1); l, t, r, b = f.getbbox(e['text'])
        if r - l > total - 10 or b - t > w * 0.55: break
        size += 1
    f = ImageFont.truetype(font, size); l, t, r, b = f.getbbox(e['text'])
    flat = Image.new('L', (total, w), 0)
    ImageDraw.Draw(flat).text(((total - (r - l)) // 2 - l, (w - (b - t)) // 2 - t), e['text'], font=f, fill=255)
    mask = flat.rotate(-90, expand=True)                  # (w, total): reads top to bottom, letter tops to the right
    halo = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(3))
    soft = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(5))
    y = 0
    for n, h in zip(names, hs):
        old = imgs[n].astype(np.float32); a = old[..., 3]
        amax = a.max() or 255
        hi = old[a >= 0.75 * amax][:, :3]; mid = old[(a > 0.15 * amax) & (a < 0.6 * amax)][:, :3]
        core_c = hi.mean(0) if len(hi) else np.array([255, 255, 255.])
        halo_c = mid.mean(0) if len(mid) else core_c
        crisp = (a >= 0.75 * amax).sum() > 0.25 * (a > 0.15 * amax).sum()    # a bright line, not just a glow layer
        part = lambda im: np.array(im)[y:y + h].astype(np.float32) / 255
        if crisp:
            ca, ha = part(mask), part(halo) * 0.8
            alpha = ca + ha * (1 - ca)
            rgb = (core_c * ca[..., None] + halo_c * (ha * (1 - ca))[..., None]) / np.maximum(alpha, 1e-6)[..., None]
        else:
            alpha = np.clip(part(soft) * 1.6, 0, 1); rgb = np.broadcast_to(halo_c, alpha.shape + (3,))
        imgs[n][:] = np.dstack([rgb, alpha * amax]).clip(0, 255).astype(np.uint8)
        y += h


def draw_mesh(img, e, pieces):
    """Text drawn through a window model (SGARC mini-games): {"clump": N, "tex": T, "items": [{"box": [x0, y0, x1, y1],
    "text": "..."}], "layout": "row" (optional), "geo": [k...] (optional)}. Boxes are screen rects in model units
    (y up, as tools/rwgeo.py prints them). The English is drawn on a screen canvas, then every texel the clump's
    triangles show inside a box takes the canvas pixel at its screen position, so words may span atlas pieces."""
    import rwgeo
    h, w = img.shape[:2]
    ps = [p for p in pieces if p['clump'] == e['clump'] and p['tex'] == e['tex'] and ('geo' not in e or p['geo'] in e['geo'])]
    if not ps: raise KeyError(f'{e["member"]}: clump {e["clump"]} does not draw {e["tex"]}')
    mask, sx, sy = rwgeo.texel_screen(ps, (w, h), e.get('layout'))
    S = 4                                                        # canvas supersampling
    boxes = [it['box'] for it in e['items']]
    X0 = min(b[0] for b in boxes); Y1 = max(b[3] for b in boxes)
    X1 = max(b[2] for b in boxes); Y0 = min(b[1] for b in boxes)
    cw, ch = int((X1 - X0) * S) + 2, int((Y1 - Y0) * S) + 2
    inside = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in boxes: inside |= mask & (sx >= x0) & (sx <= x1) & (sy >= y0) & (sy <= y1)
    if 'texels' in e:                                            # only these texels (others are shared decorations)
        tx0, ty0, tx1, ty1 = e['texels']; lim = np.zeros_like(inside); lim[ty0:ty1, tx0:tx1] = True; inside &= lim
    if not inside.any(): raise ValueError(f'{e["tex"]}: no texel of clump {e["clump"]} inside the boxes')
    light, dark = _inks(img[inside][None])
    fill, edge = tuple(e.get('fill', light)) + (255,), tuple(e.get('edge', dark)) + (255,)
    stroke = e.get('stroke', 2) * S
    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0)); dr = ImageDraw.Draw(canvas)
    font_path = FONTS[e.get('font', 'bold')]
    for it in e['items']:
        x0, y0, x1, y1 = it['box']
        bx0, by0, bw, bh = (x0 - X0) * S, (Y1 - y1) * S, (x1 - x0) * S, (y1 - y0) * S
        size = 6
        while size < 400:
            f = ImageFont.truetype(font_path, size + 2)
            l, t, r, b = dr.multiline_textbbox((0, 0), it['text'], font=f, stroke_width=stroke, spacing=0, align='center')
            if r - l > bw * 0.96 or b - t > bh * it.get('fill_h', 0.8): break
            size += 2
        f = ImageFont.truetype(font_path, size)
        l, t, r, b = dr.multiline_textbbox((0, 0), it['text'], font=f, stroke_width=stroke, spacing=0, align='center')
        al = it.get('align', 'center')
        px = {'left': bx0 + S - l, 'right': bx0 + bw - S - r}.get(al, bx0 + (bw - (r - l)) / 2 - l)
        dr.multiline_text((px, by0 + (bh - (b - t)) / 2 - t), it['text'], font=f, fill=fill, stroke_width=stroke,
                          stroke_fill=edge, spacing=0, align='center')
    small = np.array(canvas.resize((max(1, cw // S), max(1, ch // S)), Image.LANCZOS))
    ys, xs = np.nonzero(inside)
    cx = np.clip(((sx[ys, xs] - X0)).astype(int), 0, small.shape[1] - 1)
    cy = np.clip(((Y1 - sy[ys, xs])).astype(int), 0, small.shape[0] - 1)
    img[ys, xs] = small[cy, cx]


def load_labels():
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'gfx', 'labels*.json'))): out += json.load(open(p, encoding='utf-8'))
    return out


def edited(member, raw_member, labels):
    """-> new member bytes (CMP-compressed like the original) with its labels drawn, and the edited images."""
    raw = bytearray(decompress(raw_member) if raw_member[:3] == b'CMP' else raw_member)
    mine = [e for e in labels if e['member'] == member]
    for e in (e for e in mine if 'move' in e):        # {"clump": N, "geo": G, "move": [dx, dy], "tex"?, "uv"?}
        import rwgeo
        rwgeo.move(raw, e['clump'], e['geo'], *e['move'], e.get('tex'), e.get('uv'))
    mine = [e for e in mine if 'move' not in e]
    imgs = {}
    texs = txd.textures(bytes(raw))
    sig = {}                                          # sigils span several textures: draw them first (draw_sigil)
    for e in (e for e in mine if 'sigil' in e):
        group = {t['name']: t['img'].copy() for t in texs if t['name'] in e['sigil']}
        if len(group) != len(e['sigil']): raise KeyError(f'{member}: no texture {sorted(set(e["sigil"]) - set(group))}')
        draw_sigil(group, e); sig.update(group)
    for t in texs:
        es = [e for e in mine if e.get('tex') == t['name']]
        if not es and t['name'] not in sig: continue
        img = sig.get(t['name'], t['img'].copy())
        for e in es:
            if 'clump' in e:
                import rwgeo
                pieces = getattr(edited, '_pieces', {}).get(member) or rwgeo.pieces(bytes(raw))
                edited._pieces = {member: pieces}
                draw_mesh(img, e, pieces)
            else: draw_label(img, e)
        pal = next((e['palette'] for e in es if 'palette' in e), None)
        put(raw, t['name'], img, pal); imgs[t['name']] = img
    missing = {e['tex'] for e in mine if 'tex' in e} - set(imgs)
    if missing: raise KeyError(f'{member}: no texture {sorted(missing)}')
    return (compress(bytes(raw)) if raw_member[:3] == b'CMP' else bytes(raw)), imgs


ARCHIVES = {'WINARC': '/WINDOW/WINARC.AFS', 'BTLARC': '/BATTLE/BTLARC.AFS', 'EFFARC': '/EFFECT/EFFARC.AFS',
            'SGARC': '/SUBGAME/SGARC.AFS'}


def build_archive(od, arc, labels=None):
    """-> AFS bytes of archive arc (WINARC, BTLARC, EFFARC: label key "archive", default WINARC) with its edits."""
    labels = [e for e in (load_labels() if labels is None else labels) if e.get('archive', 'WINARC') == arc]
    a = afs.Afs(os.path.join(od, arc + '.AFS'))
    members = [a.data(i) for i in range(len(a.ents))]
    for m in sorted({e['member'] for e in labels}): members[a.index(m)] = edited(m, members[a.index(m)], labels)[0]
    return afs.build(members, [a.meta(i) for i in range(len(a.ents))])


def build_all(od):
    """-> {disc path: AFS bytes} for every archive that has labels."""
    used = {e.get('archive', 'WINARC') for e in load_labels()}
    return {ARCHIVES[arc]: build_archive(od, arc) for arc in ARCHIVES if arc in used}


def build_winarc(od, labels=None):
    return build_archive(od, 'WINARC', labels)


if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == 'preview':
    import unpack
    od, _ = unpack.unpack()
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    rx = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
    labels = [e for e in load_labels() if not rx or rx.search(e.get('tex') or ' '.join(e['sigil']))]
    for arc, m in sorted({(e.get('archive', 'WINARC'), e['member']) for e in labels}):
        a = afs.Afs(os.path.join(od, arc + '.AFS'))
        new, imgs = edited(m, a.data(a.index(m)), [e for e in labels if e.get('archive', 'WINARC') == arc])
        for t in txd.textures(new):                       # decode what we wrote: proves the round trip
            if t['name'] not in imgs: continue
            im = Image.fromarray(t['img'], 'RGBA')
            bg = Image.new('RGBA', im.size, (40, 40, 48, 255)); bg.alpha_composite(im)
            bg.save(os.path.join(out, f'{t["name"]}.png'))
            bg.resize((im.width * 4, im.height * 4), Image.NEAREST).save(os.path.join(out, f'{t["name"]}_x4.png'))
            print(m, t['name'], 'written')
