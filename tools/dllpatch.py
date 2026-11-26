#!/usr/bin/env python3
"""Patches to the DLL screens (SN .rel modules, tools/snrel.py), applied by build.py.

W_SY05 (name entry / password keyboard, decision D23):
- mj_sp @0x3428 holds four 0xD0-byte pages of 2-byte SJIS cells: symbols @+0x60, ABC @+0x130, katakana @+0x200,
  hiragana @+0x2d0. The tabs run the other way (tab 0 = hiragana) and the screen opens on tab 0, so swapping the
  ABC and hiragana pages makes the keyboard open on A-Z (tab labels swapped to match in wsy05mes:5-9).
- max input length (@0x2e04): mode 1 (code) 7, every other mode 9; the instruction at 0x2f8c `li v0,7` becomes 9.
"""
import struct

SY05 = '/DLL/WOT/W_SY05.REL'
MJ_SP, PAGE = 0x3428, 0xD0
ABC, HIRA = MJ_SP + 0x130, MJ_SP + 0x2d0
CODE_MAX = 0x2f8c


def patch_sy05(rel):
    b = bytearray(rel)
    assert b[ABC:ABC + 2].decode('cp932') == 'Ａ' and b[HIRA:HIRA + 2].decode('cp932') == 'あ', 'W_SY05 layout'
    b[ABC:ABC + PAGE], b[HIRA:HIRA + PAGE] = b[HIRA:HIRA + PAGE], b[ABC:ABC + PAGE]
    assert struct.unpack_from('<I', b, CODE_MAX)[0] == 0x24020007, 'W_SY05 code max'   # addiu v0, zero, 7
    struct.pack_into('<I', b, CODE_MAX, 0x24020009)
    return bytes(b)


# Typed passwords (D23): FUN_00135ab8 strcmp's the keyboard entry (full-width SJIS) against four strings packed in
# 0x766bd0..0x766c18 (72 bytes), each loaded as `lui a1,0x76 ; addiu a1,a1,lo` (lo at the VAs below).
# Order: code (mode 1, Manto, ev2520), Split Rock stages 1-3 (tengu fragments DARK PLAC EHID EPEA RLOY STER, ev4007,
# ev4002, ev4037, ev4012, ev4025, ev4038 in the hint's spell order).
PASSWORDS = ['LASODO', 'DARKPLACE', 'HIDEPEARL', 'OYSTER']
PW_AREA, PW_END = 0x766bd0, 0x766c18
PW_LOADS = [0x135c14, 0x135c3c, 0x135c4c, 0x135c54]
ELF_BASE = 0xFF000


def patch_passwords(elf):
    b = bytearray(elf)
    assert b[PW_AREA - ELF_BASE:PW_AREA - ELF_BASE + 14].decode('cp932') == 'おれさまラソド', 'password area'
    blob = b''.join(p.translate({c: c + 0xFEE0 for c in range(0x21, 0x7F)}).encode('cp932') + b'\0' for p in PASSWORDS)
    assert len(blob) <= PW_END - PW_AREA and all(len(p) <= 9 for p in PASSWORDS)   # 9 = keyboard max (W_SY05)
    b[PW_AREA - ELF_BASE:PW_END - ELF_BASE] = blob.ljust(PW_END - PW_AREA, b'\0')
    addr = PW_AREA
    for va, p in zip(PW_LOADS, PASSWORDS):
        w, = struct.unpack_from('<I', b, va - ELF_BASE)
        assert w >> 16 == 0x24A5, hex(w)                   # addiu a1, a1, lo
        struct.pack_into('<I', b, va - ELF_BASE, 0x24A50000 | (addr & 0xFFFF))
        addr += len(p) * 2 + 1
    return bytes(b)


# Shop party panels print the level at x 151 like w_status_base3: moved to 180 (after the label, elfpatch 'level x').
LEVEL_X = {'/DLL/WSH/W_SH01.REL': 0x9868, '/DLL/WSH/W_SH07.REL': 0x3210}


def patch_level_x(rel, at):
    b = bytearray(rel)
    assert struct.unpack_from('<I', b, at)[0] == 0x3C014317, 'shop level x'          # lui at, 0x4317 (151.0)
    struct.pack_into('<I', b, at, 0x3C014334)                                         # 180.0
    return bytes(b)


# Map screen region name box: `li v0,22` (centring pitch, before the name's ws_printf2) becomes a jal to the ELF cave
# that sets the smaller font and returns its pitch (elfpatch MAP_*, 'map_font'); the name's y moves down to match;
# the reading row's `lui at,0x4190` calls 'map_font_rst', which puts the ASCII scale back.
MP02, MP02_SIZE = '/DLL/WOT/W_MP02.REL', 0x2474


def patch_mp02(rel):
    import elfpatch
    b = bytearray(rel)
    where = elfpatch.caves()[1]
    assert struct.unpack_from('<I', b, MP02_SIZE)[0] == 0x24020016, 'W_MP02 pitch'     # addiu v0, zero, 22
    struct.pack_into('<I', b, MP02_SIZE, elfpatch.jal(where['map_font']))
    assert struct.unpack_from('<I', b, MP02_SIZE + 0xc)[0] == 0x3C01C0C0, 'W_MP02 name y'   # lui at, -6.0
    struct.pack_into('<I', b, MP02_SIZE + 0xc, 0x3C010000 | elfpatch.MAP_Y)
    # after the name's ws_printf2: `lui at,0x4190` (reading row size 18) -> cave that puts the ASCII scale back
    assert struct.unpack_from('<I', b, MP02_SIZE + 0x38)[0] == 0x3C014190, 'W_MP02 kana size'
    struct.pack_into('<I', b, MP02_SIZE + 0x38, elfpatch.jal(where['map_font_rst']))
    return bytes(b)


def patch(od_read):
    """od_read(disc_path) -> original bytes. -> {disc_path: patched bytes}."""
    out = {SY05: patch_sy05(od_read(SY05)), MP02: patch_mp02(od_read(MP02))}
    for p, at in LEVEL_X.items(): out[p] = patch_level_x(od_read(p), at)
    return out
