#!/usr/bin/env python3
"""Release code patches for SLPM_659.52 (applied to every translated build; test-only patches: debugpatch.py).

nameplate_pitch: ws_window_mess_start (0x41d648) picks the speaker nameplate's glyph spacing from the name's
glyph count (ws_mess_data_length - 1, jump table at 0x783f70): 1/5/6 glyphs -4 (22 px pitch), 2 -> +0x12
(44 px), 3 -> 7 (33 px), 4 -> 3 (29 px), 7+ -> uninitialised stack word. `beqz v0, 0x41dc3c` (skip the
table when >= 6) becomes `b 0x41dc10` (the -4 case): 22 px for every name.

VWF (decisions.md D8; tools/vwf.py draws ASCII codes 0x00-0x5E and fills the advance table TBL = 0x783210,
u8 advance-1, which ws_printf2 already uses for codes < 0x60):
- message window (ws_window_mess_update_sub 0x41e1e0): glyph x = base + col*pitch + window[0x3d2]. The byte
  at 0x3d2 (button icons add 10 to it; 0x3d3 is padding, never accessed) becomes a signed halfword pixel
  offset; after each ASCII glyph a cave adds (advance - pitch) to it.
- line width (FUN_0041c3b8, used for centring lines and the nameplate): width = n*26 + (n-1)*adj + t9 (t9:
  10 px per button, kept as t7>>16 - 10). A cave adds (advance - 26 - adj) to t9 and t7 per ASCII glyph.
- nameplate (ws_window_mess_start): glyph x = sp[0x818] + i*pitch; a cave adds (advance - pitch) to sp[0x818].
- ws_mess_data_length (longest line in glyphs; callers size windows with it): sums pixels (ASCII advance, 22
  per other glyph, ruby readings -22 each) and returns ceil(px / 22). Japanese lines give the original counts.
Caves live in ws_debwin_menu_draw (0x41b9d0, unused debug code), between debugpatch's first 0x40 and last 0xA0 bytes.

Also (2026-11-22, user report): the opening movie plays with English captions and can be skipped (tools/opening.py);
the field-menu location line drops the country (ws_place_printf, wmn01:63); vertical text (town-name banner,
EvWindowGroupTownName: 26 px cells, 216 px strip) draws ASCII turned 90 degrees, stepped by VWF advance.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opening

BASE = 0xFF000                       # file offset = VA - BASE
TBL = 0x783210
CAVE = 0x41B9D0 + 0x40
CAVE_END = 0x41B9D0 + 1752 - 0xA0    # debugpatch's field-hook cave owns the last 0xA0 bytes
# map screen region name (mp01 + W_MP02): font 21.0 (26 overflowed the box), step x256/26, y -8.5, centring pitch
# 15 px per ws_mess_data_length unit (ceil(px/22), coarse): keeps Onigashima (6 units, 90 px) inside the ~96 px box
MAP_SIZE, MAP_K, MAP_PITCH, MAP_Y = 0x41A80000, 207, 15, 0xC108

ZERO, AT, V0, V1, A0, A1, A2, A3 = 0, 1, 2, 3, 4, 5, 6, 7
T5, T6, T7, T8, T9, S0, S1, S2, S3, SP, RA = 13, 14, 15, 24, 25, 16, 17, 18, 19, 29, 31


# --- MIPS encoders -------------------------------------------------------------------------------------
def _i(op, rs, rt, imm): return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _r(rs, rt, rd, sa, fn): return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn
def j(t): return 0x08000000 | ((t >> 2) & 0x3FFFFFF)
def beq(rs, rt, frm, to): return _i(4, rs, rt, (to - frm - 4) >> 2)
def addiu(rt, rs, imm): return _i(9, rs, rt, imm)
def sltiu(rt, rs, imm): return _i(11, rs, rt, imm)
def lui(rt, imm): return _i(15, 0, rt, imm)
def lb(rt, off, base): return _i(0x20, base, rt, off)
def lh(rt, off, base): return _i(0x21, base, rt, off)
def lw(rt, off, base): return _i(0x23, base, rt, off)
def lbu(rt, off, base): return _i(0x24, base, rt, off)
def lhu(rt, off, base): return _i(0x25, base, rt, off)
def sb(rt, off, base): return _i(0x28, base, rt, off)
def sh(rt, off, base): return _i(0x29, base, rt, off)
def sw(rt, off, base): return _i(0x2B, base, rt, off)
def swc1(ft, off, base): return _i(0x39, base, ft, off)
def addu(rd, rs, rt): return _r(rs, rt, rd, 0, 0x21)
def subu(rd, rs, rt): return _r(rs, rt, rd, 0, 0x23)
def sll(rd, rt, sa): return _r(0, rt, rd, sa, 0)
def sra(rd, rt, sa): return _r(0, rt, rd, sa, 3)
def mult(rs, rt): return _r(rs, rt, 0, 0, 0x18)
def mflo(rd): return _r(0, 0, rd, 0, 0x12)
def jr(rs): return _r(rs, 0, 0, 0, 0x08)
def jal(t): return 0x0C000000 | ((t >> 2) & 0x3FFFFFF)
def bne(rs, rt, frm, to): return _i(5, rs, rt, (to - frm - 4) >> 2)
def ori(rt, rs, imm): return _i(13, rs, rt, imm)
def andi(rt, rs, imm): return _i(12, rs, rt, imm)
def ld(rt, off, base): return _i(0x37, base, rt, off)
def sd(rt, off, base): return _i(0x3F, base, rt, off)
def move(rd, rs): return _r(rs, 0, rd, 0, 0x2D)        # daddu rd, rs, zero
NOP = 0
def b_(frm, to): return beq(ZERO, ZERO, frm, to)
def beqz(rs, frm, to): return beq(rs, ZERO, frm, to)


def hi_lo(addr):
    hi = (addr + 0x8000) >> 16; return hi, addr - (hi << 16)


class Asm:
    """Tiny assembler: list of words or ('beqz', reg, label) / ('label', name)."""
    def __init__(self, at):
        self.at, self.items = at, []
    def __call__(self, *ws): self.items.extend(ws); return self
    def build(self):
        labels, pc = {}, self.at
        for it in self.items:
            if isinstance(it, tuple) and it[0] == 'label': labels[it[1]] = pc
            else: pc += 4
        out, pc = [], self.at
        for it in self.items:
            if isinstance(it, tuple):
                if it[0] == 'label': continue
                if it[0] == 'beqz': out.append(beqz(it[1], pc, labels[it[2]]))
                elif it[0] == 'bltz': out.append(_i(1, it[1], 0, (labels[it[2]] - pc - 4) >> 2))
                elif it[0] == 'bgez': out.append(_i(1, it[1], 1, (labels[it[2]] - pc - 4) >> 2))
                elif it[0] == 'bne': out.append(bne(it[1], it[2], pc, labels[it[3]]))
                elif it[0] == 'b': out.append(b_(pc, labels[it[1]]))
            else: out.append(it)
            pc += 4
        return out


def tbl_lookup(dst, code):
    """dst = TBL[code] + 1 (advance), clobbers dst only."""
    hi, lo = hi_lo(TBL)
    return [lui(dst, hi), addu(dst, dst, code), lbu(dst, lo, dst), addiu(dst, dst, 1)]


def caves():
    """-> (list of (va, word) for the caves, {name: cave va})"""
    out, where, pc = [], {}, CAVE

    # A: message window glyph x. Entered from 0x41e9c4 (delay slot: cvt.s.w f0,f0). v1 = pitch.
    a = Asm(pc)
    a(swc1(0, 0x10, S0), lhu(A0, 0x22, S0), sltiu(V0, A0, 0x60), ('beqz', V0, 'ret'), NOP)
    a(*tbl_lookup(V0, A0))
    a(subu(V0, V0, V1), lh(A0, 0x3D2, S1), addu(A0, A0, V0), sh(A0, 0x3D2, S1))
    a(('label', 'ret'), j(0x41E9D0), NOP)
    where['msg_x'] = pc; words = a.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # B: line width. Entered from 0x41c480 (delay slot: sll v0,v0,16). a1 = code, a2 = pitch adj.
    b = Asm(pc)
    b(addiu(9, 9, 2), sra(T5, V0, 16), sltiu(V0, A1, 0x60), ('beqz', V0, 'ret'), NOP)   # 9 = t1
    b(*tbl_lookup(V1, A1))
    b(addiu(V1, V1, -26), subu(V1, V1, A2), addu(T9, T9, V1), sll(V1, V1, 16), addu(T7, T7, V1))
    b(('label', 'ret'), j(0x41C59C), NOP)
    where['width'] = pc; words = b.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # C: nameplate glyph. Entered from 0x41ddfc (delay slot: swc1 f2,0x18(s0)). v0, v1, a0 are dead.
    c = Asm(pc)
    c(lhu(V1, 0x22, S0), sltiu(V0, V1, 0x60), ('beqz', V0, 'ret'), NOP)
    c(*tbl_lookup(V0, V1))
    c(lw(A0, 0x814, SP), addiu(V0, V0, -26), subu(V0, V0, A0), lw(A0, 0x818, SP), addu(A0, A0, V0), sw(A0, 0x818, SP))
    c(('label', 'ret'), j(0x41E114), NOP)
    where['plate'] = pc; words = c.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # D: ws_mess_data_length counts pixels (a3) instead of glyphs: + advance per ASCII glyph, + 22 otherwise.
    # Entered from 0x4118b8; v1 = code.
    d = Asm(pc)
    d(sltiu(V0, V1, 0x60), ('beqz', V0, 'add'), addiu(V0, ZERO, 22))
    d(*tbl_lookup(V0, V1))
    d(('label', 'add'), addu(A3, A3, V0), j(0x41195C), NOP)
    where['len_glyph'] = pc; words = d.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # E: ruby readings (t5 += b) are subtracted at line end: count them as 22 px each. Entered from 0x41190c, v0 = b.
    e = Asm(pc)
    e(sll(T6, V0, 4), sll(T7, V0, 2), addu(T6, T6, T7), sll(T7, V0, 1), addu(T6, T6, T7), addu(T5, T5, T6))
    e(j(0x41195C), NOP)
    where['len_ruby'] = pc; words = e.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # F: return ceil(a3 / 22) = (a3 + 21) * 745 >> 14 (exact below 112 glyphs). Entered from 0x411984.
    f = Asm(pc)
    f(addiu(A3, A3, 21), addiu(T6, ZERO, 745), mult(A3, T6), mflo(V0), sra(V0, V0, 14), jr(RA), NOP)
    where['len_ret'] = pc; words = f.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # G: the opening movie (main flow, New Game) with English captions and skippable (tools/opening.py). Called from
    # 0x13b278 instead of AdxMovieProcCreate(s1, 0, 0x10013, 0); s1 = the main process.
    g = Asm(pc)
    g(addiu(SP, SP, -32), sd(RA, 0, SP), sd(S2, 8, SP), sd(S3, 16, SP))
    g(jal(0x41C0A8), NOP, move(S2, V0), ('beqz', V0, 'play'), move(S3, ZERO))          # ws_window_create
    g(move(A0, V0), addiu(A1, ZERO, opening.ST_IDX), addiu(A2, ZERO, opening.MES_IDX))
    g(jal(0x109A50), addiu(A3, ZERO, opening.OFS_IDX), move(S3, V0))                   # AdxMovieSubtitleCreate
    g(('label', 'play'), move(A0, S1), move(A1, S3), lui(A2, 1), ori(A2, A2, 0x13))
    g(jal(0x109948), addiu(A3, ZERO, 1))                                                # AdxMovieProcCreate, skippable
    g(('beqz', S3, 'out'), NOP, jal(0x109B98), move(A0, S3))                           # AdxMovieSubTitleDelete
    g(jal(0x41C2D0), move(A0, S2))                                                      # ws_window_delete
    g(('label', 'out'), ld(RA, 0, SP), ld(S2, 8, SP), ld(S3, 16, SP), jr(RA), addiu(SP, SP, 32))
    where['opening'] = pc; words = g.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # Vertical text (ws_printf2, e.g. the town-name banner) sets English sideways: ASCII glyphs turned 90 degrees
    # clockwise, stepped down by their VWF advance instead of 27 px.
    # H: y step. Entered by `bnez v0` at 0x40d5c4 (vertical ASCII; delay slot v0 = s3 + 27). s1 = code pointer.
    h = Asm(pc)
    h(lhu(T8, 0, S1), *tbl_lookup(T9, T8), addu(V0, 19, T9), j(0x40D648), NOP)         # 19 = s3 (y offset)
    where['vert_step'] = pc; words = h.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # I: glyph flags (font state 0x6f15) get 0x10 = "turned" for ASCII in vertical mode. From 0x40d680, v1 = font state.
    i = Asm(pc)
    i(lbu(V0, 0x6F15, V1), lbu(T8, 0x6F14, V1), ('beqz', T8, 'st'), NOP)
    i(lhu(T9, 0, S1), sltiu(T9, T9, 0x60), ('beqz', T9, 'st'), NOP, ori(V0, V0, 0x10))
    i(('label', 'st'), sb(V0, 0xC0, SP), j(0x40D688), NOP)
    where['vert_flag'] = pc; words = i.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # R: after FNTSetPrimUv (0x410880) a turned glyph swaps v of vertices 0/3 and u of vertices 1/2 (strip TL, BL,
    # TR, BR at 0x79fca0, 0x40 bytes each; u/v at +0x10/+0x14): the cell is drawn rotated 90 degrees clockwise.
    r = Asm(pc)
    r(lbu(T8, 0x20, S0), andi(T8, T8, 0x10), ('beqz', T8, 'done'), NOP, lui(AT, 0x7A))
    r(lw(T8, -0x34C, AT), lw(T9, -0x28C, AT), sw(T9, -0x34C, AT), sw(T8, -0x28C, AT))
    r(lw(T8, -0x310, AT), lw(T9, -0x2D0, AT), sw(T9, -0x310, AT), sw(T8, -0x2D0, AT))
    r(('label', 'done'), lbu(V0, 0x21, S0), j(0x410890), NOP)
    where['turn_uv'] = pc; words = r.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # ASCII scale. ws_printf2 draws codes < 0x60 at a fixed 26 px, stepped by the VWF table, whatever the font size
    # (two copies of that path: 0x40cfec and 0x40d5ac). They now read ASC_SIZE (float glyph size) and ASC_K (step
    # x/256), 26.0 and 256 unless a caller below sets them: only the map region name does (MAP_SIZE, 26 overflowed
    # its box), and puts them back right after its ws_printf2.
    asc = pc; out += [(pc, 0x41D00000), (pc + 4, 256)]; pc += 8
    where['asc_size'], where['asc_k'] = asc, asc + 4
    ah, al = (asc + 0x8000) >> 16, asc & 0xFFFF
    assert (asc + 4) >> 15 == asc >> 15
    S5 = 21
    SMALL, SMALL_K = MAP_SIZE, MAP_K
    def asc_set(f, k): return [lui(AT, f >> 16), sw(AT, 0, T9), addiu(AT, ZERO, k), sw(AT, 4, T9)]
    for n, back in (('asc_adv1', 0x40D090), ('asc_adv2', 0x40D650)):
        # entered from `andi v1,s5,0xffff` (delay slot `addu v0,sp,v0`): v0 = &width[code]
        a_ = Asm(pc)
        a_(lbu(V0, 0, V0), addiu(V0, V0, 1), lui(AT, ah), lw(AT, (al + 4) & 0xFFFF, AT))
        a_(0x00411018, addiu(V0, V0, 128), sra(V0, V0, 8))                        # mult v0, v0, at (R5900)
        a_(andi(V1, S5, 0xFFFF), addu(V1, V1, V0), sll(V1, V1, 16), j(back), sra(S5, V1, 16))
        where[n] = pc; words = a_.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # M (W_MP02 0x2474, dllpatch.MP02_SIZE, replaces `li v0,22`): ws_font_set_size(20) inlined (font work
    # 0x5cac38 +0x6f04/+0x6f08), ASCII scale small, returns v0 = MAP_PITCH, the module's centring pitch (22 originally).
    m = Asm(pc)
    m(lui(T9, ah), addiu(T9, T9, al), *asc_set(SMALL, SMALL_K))
    m(lui(V0, 0x5D), lw(V0, -0x53C8, V0), ('beqz', V0, 'ret'), lui(AT, SMALL >> 16))
    m(0x44810000, 0xE4406F04, 0xE4406F08)                          # mtc1 at,f0 ; swc1 f0,0x6f04(v0) ; swc1 f0,0x6f08(v0)
    m(('label', 'ret'), jr(RA), addiu(V0, ZERO, MAP_PITCH))
    where['map_font'] = pc; words = m.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # MR (W_MP02 0x24ac, replaces `lui at,0x4190` before the reading row's ws_font_set_size): scale back, f12 = 18.0
    r_ = Asm(pc)
    r_(lui(T9, ah), addiu(T9, T9, al), *asc_set(0x41D00000, 256), lui(AT, 0x4190), 0x44816000, jr(RA), NOP)
    where['map_font_rst'] = pc; words = r_.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # MD (mp01 0x3ffdc4, replaces jal ws_font_set_default): default font, ASCII scale small, ws_font_set_size(20).
    md_ = Asm(pc)
    md_(addiu(SP, SP, -16), sd(RA, 0, SP), jal(0x40CB08), NOP, ld(RA, 0, SP), addiu(SP, SP, 16))
    md_(lui(T9, ah), addiu(T9, T9, al), *asc_set(SMALL, SMALL_K))
    md_(lui(AT, SMALL >> 16), 0x44816000, j(0x40CBC0), 0x46006346)   # mtc1 at,f12 ; j ws_font_set_size ; mov.s f13,f12
    where['map_font_def'] = pc; words = md_.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # MC (mp01 0x3ffe14, replaces jal ws_font_set_color after the name): scale back, then ws_font_set_color.
    mc = Asm(pc)
    mc(lui(T9, ah), addiu(T9, T9, al), *asc_set(0x41D00000, 256), j(0x40CB80), NOP)
    where['map_font_col'] = pc; words = mc.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)

    # Movie subtitles for movies whose scripts request none (title cards, tools/opening.py). s0 = 0x7c7778:
    # 0x17c = movie id, 0x1b0/0x1b4/0x1b8 = subtitle st/mes/ofs file indices (-1 = none). SF fills them from the
    # table (id, st, mes, ofs; id -1 ends) and returns v0 = 0x1b0. SA/SB replace the two `0x1b0 < 0` tests.
    table = opening.card_table()
    tab_va = pc; tw = [v for row in table for v in row] + [0xFFFFFFFF]
    out += [(pc + 4 * k, w & 0xFFFFFFFF) for k, w in enumerate(tw)]; pc += 4 * len(tw)
    s = Asm(pc)
    s(lw(V0, 0x1B0, S0), ('bgez', V0, 'ret'), NOP, lw(T8, 0x17C, S0))
    s(lui(T9, (tab_va + 0x8000) >> 16), addiu(T9, T9, tab_va & 0xFFFF))
    s(('label', 'loop'), lw(V1, 0, T9), ('bltz', V1, 'ret'), NOP, ('bne', V1, T8, 'next'), NOP)
    s(lw(V1, 4, T9), sw(V1, 0x1B0, S0), lw(V1, 8, T9), sw(V1, 0x1B4, S0), lw(V1, 12, T9), sw(V1, 0x1B8, S0))
    s(('b', 'ret'), NOP)
    s(('label', 'next'), addiu(T9, T9, 16), ('b', 'loop'), NOP)
    s(('label', 'ret'), lw(V0, 0x1B0, S0), jr(RA), NOP)
    where['sub_fill'] = pc; words = s.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # SA: FUN_00137758 at 0x1377e0 (`bltzl v0, 0x137810` / likely slot `lw v0, 0x1ac(s0)`)
    sa = Asm(pc)
    sa(jal(where['sub_fill']), NOP, ('bltz', V0, 'none'), NOP, j(0x1377E8), NOP)
    sa(('label', 'none'), lw(V0, 0x1AC, S0), j(0x137810), NOP)
    where['sub_a'] = pc; words = sa.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    # SB: FUN_00136988 at 0x136af0 (`lw v0, 0x1b0(s0)` / `bltz v0, 0x136b20`)
    sb_ = Asm(pc)
    sb_(jal(where['sub_fill']), NOP, ('bltz', V0, 'none'), NOP, j(0x136AFC), NOP)
    sb_(('label', 'none'), j(0x136B20), NOP)
    where['sub_b'] = pc; words = sb_.build(); out += [(pc + 4 * k, w) for k, w in enumerate(words)]; pc += 4 * len(words)
    assert pc <= CAVE_END
    return out, where


def patch_list():
    """(name, va, original word, new word); caves are checked separately (their original bytes are code
    of the unused ws_debwin_menu_draw)."""
    cv, where = caves()
    P = [
        ('nameplate_pitch', 0x41DBF0, beqz(V0, 0x41DBF0, 0x41DC3C), b_(0x41DBF0, 0x41DC10)),
        # window[0x3d2] byte -> signed halfword
        ('x_off reset 1', 0x41D72C, sb(ZERO, 0x3D2, S1), sh(ZERO, 0x3D2, S1)),
        ('x_off reset 2', 0x41E2C0, sb(ZERO, 0x3D2, S1), sh(ZERO, 0x3D2, S1)),
        ('x_off reset 3', 0x41E3BC, sb(ZERO, 0x3D2, S1), sh(ZERO, 0x3D2, S1)),
        ('x_off button x', 0x41E788, lbu(V0, 0x3D2, S1), lh(V0, 0x3D2, S1)),
        ('x_off button +10 load', 0x41E7D4, lbu(A1, 0x3D2, S1), lh(A1, 0x3D2, S1)),
        ('x_off button +10 store', 0x41E7F0, sb(A1, 0x3D2, S1), sh(A1, 0x3D2, S1)),
        ('x_off glyph x', 0x41E9B4, lbu(A0, 0x3D2, S1), lh(A0, 0x3D2, S1)),
        # hooks
        ('vwf msg hook', 0x41E9C4, NOP, j(where['msg_x'])),
        ('vwf msg store', 0x41E9CC, swc1(0, 0x10, S0), NOP),     # done in the cave (j skips back past it)
        ('vwf width hook', 0x41C480, addiu(9, 9, 2), j(where['width'])),
        ('vwf plate hook', 0x41DDFC, b_(0x41DDFC, 0x41E114), j(where['plate'])),
        # ws_mess_data_length (window sizing, ~40 callers): pixels -> glyph-equivalents of 22 px
        ('len glyph hook', 0x4118B8, sll(V0, V0, 16), j(where['len_glyph'])),
        ('len glyph hook delay', 0x4118BC, b_(0x4118BC, 0x41195C), NOP),
        ('len ruby hook', 0x41190C, addu(V0, V0, T5), j(where['len_ruby'])),
        ('len ruby hook delay', 0x411910, sll(V0, V0, 16), NOP),
        ('len return hook', 0x411984, jr(RA), j(where['len_ret'])),
        ('len return hook delay', 0x411988, 0x00E0102D, NOP),     # daddu v0, a3, zero
        # Reading labels (spell/item name echoed top right, D9): right-aligned at x = 608 - (n-1)*15 from the glyph
        # count, so English ran off screen. Cave F leaves a3 = pixel width + 21: use x = 626 - px (same right edge).
        ('kana x px', 0x414F14, addiu(V0, V0, -1), addiu(V1, A3, -21)),                     # ws_kana_printf
        ('kana x right', 0x414F18, addiu(A2, ZERO, 0x260), addiu(A2, ZERO, 626)),
        ('kana x *16', 0x414F1C, sll(V1, V0, 4), NOP),
        ('kana x -n', 0x414F28, subu(V1, V1, V0), NOP),
        ('help kana right', 0x23363C, addiu(S0, ZERO, 0x260), addiu(S0, ZERO, 626)),       # battle help (FUN_00233550)
        ('help kana px', 0x233640, addiu(V0, V0, -1), addiu(V1, A3, -21)),
        ('help kana *16', 0x233644, sll(V1, V0, 4), NOP),
        ('help kana -n', 0x233648, subu(V1, V1, V0), NOP),
        # Level number after its label ("Level 40", not "40 段"): the label quads move left (gfx/labels_level.json)
        # and every level print moves right by the label's width (29 px; 32 where the label sat 1 px further
        # out); `lui at, hi` is the float x passed in f12. Spacing checked in game with 2-digit levels.
        ('level x status_base', 0x3CCDE0, lui(AT, 0x42FA), lui(AT, 0x431A)),            # 125 -> 154 menu party
        ('level x status_base2', 0x3CD014, lui(AT, 0x42FA), lui(AT, 0x431A)),           # same panel, formation
        ('level x status_base3', 0x3CD1E8, lui(AT, 0x4317), lui(AT, 0x4334)),           # 151 -> 180 equip
        ('level x status_base4', 0x3CD3B4, lui(AT, 0x4308), lui(AT, 0x4328)),           # 136 -> 168 status screen
        # map screen region box (mp01): name in font size 21, centred with MAP_PITCH, 2.5 px lower (was 26 / 22 / -6:
        # overflowed the box)
        ('map region pitch', 0x3FFD74, addiu(V1, ZERO, 22), addiu(V1, ZERO, MAP_PITCH)),
        ('map region y', 0x3FFDE4, lui(AT, 0xC0C0), lui(AT, MAP_Y)),
        ('map region size', 0x3FFDC4, jal(0x40CB08), jal(where['map_font_def'])),
        ('map region size back', 0x3FFE14, jal(0x40CB80), jal(where['map_font_col'])),
        # ws_printf2 ASCII glyphs: size from ASC_SIZE (was 26.0), step scaled by ASC_K (caves 'asc_adv1/2')
        ('ascii size 1 hi', 0x40CFEC, lui(AT, 0x41D0), lui(AT, (where['asc_size'] + 0x8000) >> 16)),
        ('ascii size 1 lo', 0x40CFF0, 0x44810000, _i(0x31, AT, 0, where['asc_size'] & 0xFFFF)),   # mtc1 -> lwc1 f0
        ('ascii step 1', 0x40D010, andi(V1, 21, 0xFFFF), j(where['asc_adv1'])),
        ('ascii size 2 hi', 0x40D5AC, lui(AT, 0x41D0), lui(AT, (where['asc_size'] + 0x8000) >> 16)),
        ('ascii size 2 lo', 0x40D5B0, 0x44810000, _i(0x31, AT, 0, where['asc_size'] & 0xFFFF)),
        ('ascii step 2', 0x40D5D0, andi(V1, 21, 0xFFFF), j(where['asc_adv2'])),
        ('level x battle 1', 0x22A3E4, lui(AT, 0x4308), lui(AT, 0x4328)),
        ('level x battle 2', 0x236AFC, lui(AT, 0x4040), lui(AT, 0x4200)),               # 3 -> 32 battle panel
        ('level x 405ccc', 0x405CB4, lui(AT, 0x4080), lui(AT, 0x4204)),                 # 4 -> 33
        ('level x 40a4a4', 0x40A48C, lui(AT, 0x4080), lui(AT, 0x4204)),
        # opening movie: captions + skippable (cave G, tools/opening.py); archives gain the caption files
        ('opening call', 0x13B278, move(A1, ZERO), jal(where['opening'])),
        ('opening a2', 0x13B27C, ori(A2, A2, 0x13), NOP),
        ('opening jal', 0x13B280, jal(0x109948), NOP),
        ('opening a3', 0x13B284, move(A3, ZERO), NOP),
        ('DATAARC count', 0x13B06C, addiu(A2, ZERO, opening.DATAARC_N), addiu(A2, ZERO, opening.DATAARC_N + opening.DATAARC_ADDED)),
        ('MESARC count', 0x13B0C0, addiu(A2, ZERO, opening.MESARC_N), addiu(A2, ZERO, opening.MESARC_N + opening.MESARC_ADDED)),
        # movie subtitles from our table when the script requested none (title cards; caves SF/SA/SB)
        ('movie subs A', 0x1377E0, _i(1, V0, 2, (0x137810 - 0x1377E0 - 4) >> 2), j(where['sub_a'])),   # bltzl
        ('movie subs B', 0x136AF0, lw(V0, 0x1B0, S0), j(where['sub_b'])),
        ('movie subs B slot', 0x136AF4, _i(1, V0, 0, (0x136B20 - 0x136AF4 - 4) >> 2), NOP),
        # field menu location (ws_place_printf): the three-part line prints location/area (wmn01:63 has two {var}),
        # country/location/area overflowed the box in English
        ('location a3', 0x4149D8, move(A3, S1), move(A3, S3)),
        ('location a1', 0x4149E0, move(A1, S3), move(A1, 20)),     # 20 = s4 (location name)
        ('location a2', 0x4149E8, move(A2, 20), move(A2, S1)),     # s1 = area name
        # vertical text: English sideways (caves H, I, R)
        ('vert step', 0x40D5C4, bne(V0, ZERO, 0x40D5C4, 0x40D648), bne(V0, ZERO, 0x40D5C4, where['vert_step'])),
        ('vert flag', 0x40D680, lbu(V0, 0x6F15, V1), j(where['vert_flag'])),
        ('turn uv', 0x410888, lbu(V0, 0x21, S0), j(where['turn_uv'])),
    ]
    return P, cv


# Data: the memory-card browser label (icon.sys, MCSysFileCreate in the save code FUN_00406980), full-width SJIS.
# Line 2 gets the save number poked into bytes 12-15 ('０' + n), so its first 6 characters must stay 6 characters.
FW = lambda s: ''.join(chr(ord(c) + 0xFEE0) if '!' <= c <= '~' else '　' if c == ' ' else c for c in s).encode('cp932')
DATA = [
    ('card title', 0x782E48, '天外魔境３　ＮＡＭＩＤＡ'.encode('cp932'), FW('Tengai Makyou3'), 32),
    ('card line 2', 0x782E18, '記録データ：００'.encode('cp932'), FW('NAMIDA00'), 24),
]


def patch(elf, widths=None):
    """widths: bytes for TBL (tools/vwf.width_table); None leaves the table alone."""
    d = bytearray(elf)
    for name, va, old, new, room in DATA:
        o = va - BASE
        assert d[o:o + len(old) + 1] == old + b'\0', f'{name}: unexpected data at {va:#x}'
        assert len(new) < room, name
        d[o:o + room] = new.ljust(room, b'\0')
    P, cv = patch_list()
    for name, va, old, new in P:
        cur = struct.unpack_from('<I', d, va - BASE)[0]
        assert cur == old, f'{name}: unexpected code at {va:#x}: {cur:#010x} (expected {old:#010x})'
        struct.pack_into('<I', d, va - BASE, new)
    for va, w in cv:
        struct.pack_into('<I', d, va - BASE, w)
    if widths is not None:
        assert len(widths) == 0x60
        d[TBL - BASE:TBL - BASE + 0x60] = widths
    return bytes(d)
