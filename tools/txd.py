#!/usr/bin/env python3
"""RenderWare PS2 native textures (chunk 0x15) inside Namida .crp2/.cmp files -> PNG.

Raster info (struct, 0x40 B): width, height, depth, rasterFormat, tex0 (u64), tex1 (u64), miptbp1, miptbp2,
pixel size, palette size, gpu size, skyMipmapVal. Pixel/palette data carry an 80-byte GS upload header when
rasterFormat & 0x20000; the TRXREG in it gives the upload size: when it differs from width x height the
pixels are swizzled (8 bpp sent as PSMCT32). Palettes: 32-bit RGBA, alpha 0..0x80, 8 bpp in CSM1 order.

usage: txd.py dump FILE.. --out DIR      (one PNG per texture, name = file_texname.png)
library: textures(raw_bytes) -> [dict(name, w, h, depth, img (H,W,4) uint8 or None, why)]
"""
import os, struct, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmp import decompress


def chunks(d, o, end):
    while o + 12 <= end:
        t, sz, ver = struct.unpack_from('<III', d, o)
        if sz > end - o - 12 or (ver >> 16) not in (0x1C02, 0x1803, 0x1003, 0x0C02, 0x3):  # sanity
            return
        yield t, o + 12, sz
        o += 12 + sz


def find_native(d, o=0, end=None, depth=0):
    end = len(d) if end is None else end
    for t, p, sz in chunks(d, o, end):
        if t == 0x15: yield p, sz
        elif t in (0x16, 0x10, 0x0E, 0x1A, 0x14, 0x253F2FE, 0x07, 0x06) and depth < 6:
            yield from find_native(d, p, p + sz, depth + 1)


def _unswizzle8(buf, w, h):
    y, x = np.mgrid[0:h, 0:w]
    block = (y & ~0xF) * w + (x & ~0xF) * 2
    swap = (((y + 2) >> 2) & 1) * 4
    posy = (((y & ~3) >> 1) + (y & 1)) & 7
    col = posy * w * 2 + ((x + swap) & 7) * 4
    byte = ((y >> 1) & 1) + ((x >> 2) & 2)
    idx = block + col + byte
    src = np.frombuffer(buf, np.uint8)
    return src[np.clip(idx, 0, len(src) - 1)]


BT32 = [[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23],
        [8, 9, 12, 13, 24, 25, 28, 29], [10, 11, 14, 15, 26, 27, 30, 31]]
CT32 = [[0, 1, 4, 5, 8, 9, 12, 13], [2, 3, 6, 7, 10, 11, 14, 15], [16, 17, 20, 21, 24, 25, 28, 29],
        [18, 19, 22, 23, 26, 27, 30, 31], [32, 33, 36, 37, 40, 41, 44, 45], [34, 35, 38, 39, 42, 43, 46, 47],
        [48, 49, 52, 53, 56, 57, 60, 61], [50, 51, 54, 55, 58, 59, 62, 63]]
BT4 = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15],
       [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30], [21, 23, 29, 31]]
_CT4_HALF = [
    [0, 8, 32, 40, 64, 72, 96, 104, 2, 10, 34, 42, 66, 74, 98, 106, 4, 12, 36, 44, 68, 76, 100, 108, 6, 14, 38, 46, 70, 78, 102, 110],
    [16, 24, 48, 56, 80, 88, 112, 120, 18, 26, 50, 58, 82, 90, 114, 122, 20, 28, 52, 60, 84, 92, 116, 124, 22, 30, 54, 62, 86, 94, 118, 126],
    [65, 73, 97, 105, 1, 9, 33, 41, 67, 75, 99, 107, 3, 11, 35, 43, 69, 77, 101, 109, 5, 13, 37, 45, 71, 79, 103, 111, 7, 15, 39, 47],
    [81, 89, 113, 121, 17, 25, 49, 57, 83, 91, 115, 123, 19, 27, 51, 59, 85, 93, 117, 125, 21, 29, 53, 61, 87, 95, 119, 127, 23, 31, 55, 63],
    [192, 200, 224, 232, 128, 136, 160, 168, 194, 202, 226, 234, 130, 138, 162, 170, 196, 204, 228, 236, 132, 140, 164, 172, 198, 206, 230, 238, 134, 142, 166, 174],
    [208, 216, 240, 248, 144, 152, 176, 184, 210, 218, 242, 250, 146, 154, 178, 186, 212, 220, 244, 252, 148, 156, 180, 188, 214, 222, 246, 254, 150, 158, 182, 190],
    [129, 137, 161, 169, 193, 201, 225, 233, 131, 139, 163, 171, 195, 203, 227, 235, 133, 141, 165, 173, 197, 205, 229, 237, 135, 143, 167, 175, 199, 207, 231, 239],
    [145, 153, 177, 185, 209, 217, 241, 249, 147, 155, 179, 187, 211, 219, 243, 251, 149, 157, 181, 189, 213, 221, 245, 253, 151, 159, 183, 191, 215, 223, 247, 255]]
CT4 = _CT4_HALF + [[v + 256 for v in r] for r in _CT4_HALF]


def _unswizzle4(buf, w, h, tw, th):
    """4 bpp texture uploaded as PSMCT32 tw x th: emulate GS memory (write CT32, read PSMT4)."""
    bt32, ct32, bt4, ct4 = map(np.array, (BT32, CT32, BT4, CT4))
    words = np.frombuffer(buf[:tw * th * 4].ljust(tw * th * 4, b'\0'), '<u4')
    dbw = max(1, tw // 64)
    y, x = np.mgrid[0:th, 0:tw]
    addr = ((y // 32) * dbw + x // 64) * 2048 + bt32[(y % 32) // 8, (x % 64) // 8] * 64 + ct32[y % 8, x % 8]
    mem = np.zeros(int(addr.max()) + 2048, '<u4'); mem[addr.reshape(-1)] = words
    nib = np.empty(mem.size * 8, np.uint8)
    for k in range(8): nib[k::8] = (mem >> (4 * k)) & 15
    tbw = max(2, (w + 63) // 64)
    y, x = np.mgrid[0:h, 0:w]
    a4 = ((y // 128) * (tbw // 2) + x // 128) * 16384 + bt4[(y % 128) // 16, (x % 128) // 32] * 512 + ct4[y % 16, x % 32]
    return nib[np.clip(a4, 0, nib.size - 1)]


BT16 = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15],
        [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30], [21, 23, 29, 31]]
CT16 = [[0, 2, 8, 10, 16, 18, 24, 26, 1, 3, 9, 11, 17, 19, 25, 27],
        [4, 6, 12, 14, 20, 22, 28, 30, 5, 7, 13, 15, 21, 23, 29, 31],
        [32, 34, 40, 42, 48, 50, 56, 58, 33, 35, 41, 43, 49, 51, 57, 59],
        [36, 38, 44, 46, 52, 54, 60, 62, 37, 39, 45, 47, 53, 55, 61, 63],
        [64, 66, 72, 74, 80, 82, 88, 90, 65, 67, 73, 75, 81, 83, 89, 91],
        [68, 70, 76, 78, 84, 86, 92, 94, 69, 71, 77, 79, 85, 87, 93, 95],
        [96, 98, 104, 106, 112, 114, 120, 122, 97, 99, 105, 107, 113, 115, 121, 123],
        [100, 102, 108, 110, 116, 118, 124, 126, 101, 103, 109, 111, 117, 119, 125, 127]]


def _addr16(tw, th):
    """Halfword address in GS memory of each pixel of a tw x th PSMCT16 upload (page 64x64, block 16x8)."""
    bt16, ct16 = np.array(BT16), np.array(CT16)
    dbw = max(1, tw // 64)
    y, x = np.mgrid[0:th, 0:tw]
    return ((y // 64) * dbw + x // 64) * 4096 + bt16[(y % 64) // 8, (x % 64) // 16] * 128 + ct16[y % 8, x % 16]


def _a4(w, h):
    """Nibble address in GS memory of each texel of a w x h PSMT4 texture (page 128x128, block 32x16)."""
    bt4, ct4 = np.array(BT4), np.array(CT4)
    tbw = max(2, (w + 63) // 64)
    y, x = np.mgrid[0:h, 0:w]
    return ((y // 128) * (tbw // 2) + x // 128) * 16384 + bt4[(y % 128) // 16, (x % 128) // 32] * 512 + ct4[y % 16, x % 32]


def _unswizzle4_16(buf, w, h, tw, th):
    """4 bpp texture uploaded as PSMCT16 tw x th: emulate GS memory (write CT16, read PSMT4)."""
    half = np.frombuffer(buf[:tw * th * 2].ljust(tw * th * 2, b'\0'), '<u2')
    addr = _addr16(tw, th)
    mem = np.zeros(int(addr.max()) + 4096, '<u2'); mem[addr.reshape(-1)] = half
    nib = np.empty(mem.size * 4, np.uint8)
    for k in range(4): nib[k::4] = (mem >> (4 * k)) & 15
    a4 = _a4(w, h)
    return nib[np.clip(a4, 0, nib.size - 1)]


def _csm1(n):
    i = np.arange(n)
    return (i & 0xE7) | ((i & 0x08) << 1) | ((i & 0x10) >> 1) if n == 256 else i


def decode_native(d, p, sz):
    it = list(chunks(d, p, p + sz))
    st = d[it[0][1]:it[0][1] + it[0][2]]
    name = d[it[1][1]:it[1][1] + it[1][2]].split(b'\0')[0].decode('latin1')
    outer = it[3]
    inner = list(chunks(d, outer[1], outer[1] + outer[2]))
    info = d[inner[0][1]:inner[0][1] + inner[0][2]]
    w, h, depth, rfmt = struct.unpack_from('<IIII', info, 0)
    psize, palsize = struct.unpack_from('<II', info, 0x30)
    data = d[inner[1][1]:inner[1][1] + inner[1][2]]
    res = dict(name=name, w=w, h=h, depth=depth, rfmt=rfmt, img=None, why='')
    hdr = 80 if rfmt & 0x20000 else 0
    pix = data[hdr:psize]
    tw = th = None
    if hdr:
        trx = struct.unpack_from('<II', data, 0x20)   # GIF A+D: TRXPOS @0x10, TRXREG @0x20 (rrw, rrh)
        tw, th = trx
    pal = data[psize + hdr:psize + palsize] if palsize else b''
    try:
        if depth == 8:
            n = w * h
            swz = hdr and (tw, th) != (w, h)
            idx = _unswizzle8(pix, w, h) if swz else np.frombuffer(pix[:n], np.uint8).reshape(h, w)
            pl = np.frombuffer(pal[:1024], np.uint8).reshape(-1, 4)[_csm1(256)]
            img = pl[idx]
        elif depth == 4:
            n = w * h // 2
            raw = np.frombuffer(pix[:n], np.uint8)
            idx = np.empty(n * 2, np.uint8); idx[0::2] = raw & 15; idx[1::2] = raw >> 4
            idx = idx.reshape(h, w)
            if hdr and (tw, th) != (w, h):
                if tw * th * 4 == n: idx = _unswizzle4(pix, w, h, tw, th)
                elif tw * th * 2 == n: idx = _unswizzle4_16(pix, w, h, tw, th)
                else:
                    res['why'] = f'4bpp swizzled via {tw}x{th} upload not decoded'; return res
            pl = np.frombuffer(pal[:64], np.uint8).reshape(-1, 4)
            img = pl[idx]
        elif depth == 32:
            img = np.frombuffer(pix[:w * h * 4], np.uint8).reshape(h, w, 4)
        else:
            res['why'] = f'depth {depth}'; return res
        img = img.copy(); img[..., 3] = np.minimum(255, img[..., 3].astype(np.int32) * 2)
        res['img'] = img
    except Exception as e:
        res['why'] = repr(e)
    return res


def textures(raw):
    if raw[:3] == b'CMP': raw = decompress(raw)
    out = []
    # crp2 = several top-level chunks; scan every top-level chunk for natives
    for p, sz in find_native(raw):
        try: out.append(decode_native(raw, p, sz))
        except Exception as e: out.append(dict(name='?', img=None, why=repr(e)))
    return out


if __name__ == '__main__' and sys.argv[1] == 'dump':
    from PIL import Image
    args = sys.argv[2:]; out = args[args.index('--out') + 1]; files = args[:args.index('--out')]
    os.makedirs(out, exist_ok=True)
    for f in files:
        base = os.path.basename(f).split('.')[0]
        for k, t in enumerate(textures(open(f, 'rb').read())):
            if t['img'] is None:
                print(f, t.get('name'), 'skip', t.get('why')); continue
            Image.fromarray(t['img'], 'RGBA').save(os.path.join(out, f'{base}_{k:02d}_{t["name"]}.png'))
