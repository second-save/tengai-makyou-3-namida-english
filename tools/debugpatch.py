#!/usr/bin/env python3
"""Test-build patches for SLPM_659.52 (never in a release build).

Pad mailbox: ReadAllPad stores held buttons with `nor a0,zero,a0; ... sh a0,(0x791f20+pad*2)`.
0x1060ac `nor` becomes `j CAVE`; the cave does the nor, ORs in the u16 at MAILBOX, jumps back.
The cave lives in ws_debwin_menu_draw (0x41b9d0, 1752 B, an unused debug function: no jal, no
pointer besides the export table, not imported by any DLL). PINE writes MAILBOX to press buttons.

Button bits (held polarity): SELECT 0x1 L3 0x2 R3 0x4 START 0x8 UP 0x10 RIGHT 0x20 DOWN 0x40 LEFT 0x80
L2 0x100 R2 0x200 L1 0x400 R1 0x800 TRIANGLE 0x1000 CIRCLE 0x2000 CROSS 0x4000 SQUARE 0x8000

Movie skip (warp tool): after the title, the main flow (0x13b258) plays the opening movie when the title's result
is 0 (New Game), then GameMainCreate. 0x13b270 (`lui a2,1`, movie args) becomes `j SKIP_CAVE`: if the u16 at
SKIP is non-zero, go straight to GameMainCreate (0x13b288). Set it via PINE (route `poke16`) with `warp`.

Forced battle (route `battle N`): the field player update (FUN_0013a1d8) calls FUN_00138810 every frame in free
roam (the step-encounter check). Its first instruction becomes `j ENC_CAVE`: if the u16 at ENC is non-zero, clear
it and tail-call EvEncountForce(-1, ENC-1, -1, 0) = formation ENC-1 of the current world's encounter table
(0x7c78f8), default battle background, default monster group, not a boss battle. Normal encounters need trigger
zones (types 6/10 in the map attributes) that set 0x7c7900/0x7c7906; a warp without story flags may have none.
Same cave, route `window TYPE ARG`: if the u16 at WIN is non-zero, clear it and tail-call EvWindowCall(WIN-1, ARG, 0),
which opens a DLL screen (table 0x586c60): 0-6 w_sh01-07, 7-0xd w_ki01-06/08, 0xe w_sy02, 0xf w_sy05 (name entry),
0x10 w_ms02, 0x11 w_sg01, 0x12/0x13 w_dj01_01/04, 0x14 w_mp01 (map). ARG = shop number for shops (shop_no_set).
Route `event CLASS METHOD`: if the u32 at EV_CLASS is non-zero, clear it and tail-call 0x132c98(0, EV_CLASS,
EV_METHOD), which starts an event-script process at that method (as the engine does for "ev1013"/"出航"). The
pointers are the module's own strings (tools/pcsx2.py looks them up in the loaded modules, list at 0x7932e8).
Route `call FN A0 A1 A2 A3`: tail-call any function from the field update (e.g. PartyItemAdd, PartyMoneyAdd,
PlayerSkillMagicAdd) to set up party state for screens that need it.
"""
import struct

BASE = 0xFF000                       # file offset = VA - BASE
HOOK = 0x1060AC
CAVE = 0x41B9D0
# Mailbox must sit on a data page: PCSX2 write-protects pages it compiled code from, and a PINE write
# there crashes the emulator (SIGBUS under Rosetta). Use the middle of a debug-only error string
# ("ev error : 配列アクセスエラー : %s(%d %d)" @ 0x765dd8, printed only on a script error).
MAILBOX = 0x765DE0
SKIP = MAILBOX + 4                   # u16: non-zero = skip the opening movie after New Game
MOVIE_HOOK, MOVIE_DONE = 0x13B270, 0x13B288
SKIP_CAVE = CAVE + 0x18              # after the pad cave; elfpatch's caves start at CAVE + 0x40
ENC = MAILBOX + 6                    # u16: formation index + 1 to force a battle (cleared when taken)
ENC_HOOK, ENC_FORCE = 0x138810, 0x137080
WIN, WIN_ARG = MAILBOX + 8, MAILBOX + 10   # u16 window type + 1 (cleared when taken), u16 its argument
WIN_CALL = 0x135998                  # EvWindowCall
EV_CLASS, EV_METHOD = MAILBOX + 12, MAILBOX + 16   # u32 string pointers (cleared when taken)
EV_START = 0x132C98                  # (0, class, method): Ev_ProcessCreate + EV_MethodCall
# Route `call FN [ARGS]`: u32 function address (cleared when taken) + 4 u32 args, in the next debug-only string
# ("no search function %s\n" @ 0x765e14, printed only when a script names a missing function).
CALL_FN = 0x765E14
CALL_ARGS = CALL_FN + 4
ENC_CAVE_SIZE = 0xA0
ENC_CAVE = CAVE + 1752 - ENC_CAVE_SIZE   # end of ws_debwin_menu_draw (elfpatch's CAVE_END)
BUTTONS = dict(select=0x1, l3=0x2, r3=0x4, start=0x8, up=0x10, right=0x20, down=0x40, left=0x80,
               l2=0x100, r2=0x200, l1=0x400, r1=0x800, triangle=0x1000, circle=0x2000, cross=0x4000, square=0x8000)

ZERO, AT, V0, A0, A1, A2, A3, T0, SP = 0, 1, 2, 4, 5, 6, 7, 8, 29


def j(t): return 0x08000000 | ((t >> 2) & 0x3FFFFFF)
def beq(rs, rt, off): return 0x10000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def nor(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x27
def or_(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x25
def lui(rt, imm): return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)
def lhu(rt, off, base): return 0x94000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def sh(rt, off, base): return 0xA4000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def lw(rt, off, base): return 0x8C000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def sw(rt, off, base): return 0xAC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def jr(rs): return (rs << 21) | 8
def addiu(rt, rs, imm): return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def hi_lo(addr):
    hi = (addr + 0x8000) >> 16; return hi, addr - (hi << 16)


def patch(elf):
    d = bytearray(elf)
    def w32(va, v): struct.pack_into('<I', d, va - BASE, v)
    def r32(va): return struct.unpack_from('<I', d, va - BASE)[0]
    assert r32(HOOK) == nor(A0, ZERO, A0), 'unexpected code at the pad hook'
    hi, lo = hi_lo(MAILBOX)
    code = [nor(A0, ZERO, A0), lui(AT, hi), lhu(AT, lo, AT), or_(A0, A0, AT), j(HOOK + 8), 0]
    for k, ins in enumerate(code): w32(CAVE + 4 * k, ins)
    w32(MAILBOX, 0)
    w32(HOOK, j(CAVE))       # delay slot = original `addiu v0,zero,4`, harmless before the cave

    assert r32(MOVIE_HOOK) == lui(A2, 1), 'unexpected code at the movie hook'
    hi, lo = hi_lo(SKIP)
    code = [lui(AT, hi), lhu(AT, lo, AT), beq(AT, ZERO, 3), 0, j(MOVIE_DONE), 0,
            lui(A2, 1), j(MOVIE_HOOK + 8), 0]          # the hook's delay slot (move a0,s1) already ran
    assert SKIP_CAVE + 4 * len(code) <= CAVE + 0x40
    for k, ins in enumerate(code): w32(SKIP_CAVE + 4 * k, ins)
    w32(SKIP, 0)
    w32(MOVIE_HOOK, j(SKIP_CAVE))

    assert r32(ENC_HOOK) == addiu(SP, SP, -0x30) and r32(ENC_HOOK + 4) == lui(V0, 0x7C), 'unexpected encounter hook'
    hi, _ = hi_lo(ENC)
    def lo(a): return a - (hi << 16)
    assert all(0 <= lo(a) < 0x8000 for a in (ENC, CALL_ARGS + 12))
    src = [lui(AT, hi), lhu(T0, lo(ENC), AT), ('beqz', T0, 'win'), 0,
           sh(ZERO, lo(ENC), AT), addiu(A1, T0, -1), addiu(A0, ZERO, -1), addiu(A2, ZERO, -1),
           j(ENC_FORCE), addiu(A3, ZERO, 0),                 # tail calls return to our caller
           'win', lhu(T0, lo(WIN), AT), ('beqz', T0, 'ev'), 0,
           sh(ZERO, lo(WIN), AT), lhu(A1, lo(WIN_ARG), AT), addiu(A0, T0, -1),
           j(WIN_CALL), addiu(A2, ZERO, 0),
           'ev', lw(T0, lo(EV_CLASS), AT), ('beqz', T0, 'call'), 0,
           sw(ZERO, lo(EV_CLASS), AT), lw(A2, lo(EV_METHOD), AT), or_(A1, T0, ZERO),
           j(EV_START), addiu(A0, ZERO, 0),
           'call', lw(T0, lo(CALL_FN), AT), ('beqz', T0, 'orig'), 0,
           sw(ZERO, lo(CALL_FN), AT), lw(A0, lo(CALL_ARGS), AT), lw(A1, lo(CALL_ARGS + 4), AT),
           lw(A2, lo(CALL_ARGS + 8), AT), jr(T0), lw(A3, lo(CALL_ARGS + 12), AT),
           'orig', addiu(SP, SP, -0x30), j(ENC_HOOK + 8), lui(V0, 0x7C)]
    labels, k = {}, 0
    for x in src:
        if isinstance(x, str): labels[x] = k
        else: k += 1
    code = []
    for x in src:
        if isinstance(x, str): continue
        if isinstance(x, tuple): x = beq(x[1], ZERO, labels[x[2]] - len(code) - 1)
        code.append(x)
    assert 4 * len(code) <= ENC_CAVE_SIZE
    for k, ins in enumerate(code): w32(ENC_CAVE + 4 * k, ins)
    w32(ENC, 0); w32(WIN, 0); w32(EV_CLASS, 0); w32(EV_METHOD, 0)
    for k in range(5): w32(CALL_FN + 4 * k, 0)
    w32(ENC_HOOK, j(ENC_CAVE))   # delay slot = original `lui v0,0x7c`, redone in the cave
    return bytes(d)
