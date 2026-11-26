# Text engine, containers and disc (SLPM-65952)

State: **verified** = roundtrip/identity tests in `tests/` pass on the real dump. In-game behaviour of
rebuilt files is **not yet verified** (no emulator on this Mac yet, see docs/status.md).

## Disc (tools/iso.py) — verified (tests/test_container.py)
- ISO9660 + UDF 1.02 bridge, 2,252,144 sectors. UDF partition start from the Partition Descriptor;
  every file is one short_ad extent. Both directory records are patched; File Entry tag CRC recomputed.
- `PADDING/PADD00-09.BIN` (10 x 100 MB filler). A grown file moves to the start of PADD00, which shrinks:
  the image size never changes. The game opens files by name (`AdxVolEntry("message/mesarc.afs")`,
  `SYSTEM/*.INF` are path lists), so the new LBA comes from the directory.
- `SLPM_659.52`: single PT_LOAD, file 0x1000 -> VA 0x100000 (file offset = VA - 0xFF000), gp 0x799e70.

## AFS (tools/afs.py) — verified identity on 6 archives
Header `AFS\0`, n, n x (off, size), (name-table off, size). Files 0x800-aligned from the header end;
name table (48 B/entry: name[32], 6 x u16 date, u32 = n) at the next boundary; file padded to 0x800.

## CMP compression (tools/cmp.py) — verified roundtrip on all 638 MESARC .cmp
`CmpDecompress` @ 0x11ac28. `CMP\0`, u32 raw size, MSB-first flag bits fetched lazily between data bytes:
`1` literal; `00LL` LL>0: len LL+1 (2-4), dist 256-b (1 byte); LL=0: u16 w, len (w&15)+1, dist 0x1000-(w>>4);
`01`+n: n=0 end, else copy n+1 bytes from dist 1. Our compressor matches the original ratio (916,721 vs 916,881 B).
Also used by `.crp2` (RenderWare TXDs).

## Messages (tools/script.py, tools/mes.py) — verified: all 27,635 strings re-encode to the original codes
- MESARC: `*mes.cmp` + `*mes.ofs` (LE u32) + `*mes.ofs.big` (same offsets BE). 637 files, ~23k unique strings.
- Decompressed (`ws_mess_data_create` @ 0x410d58): `MD`, BE u16 base (0xA72), BE u16 ncmd, BE u16 ndict,
  BE u16 start of strings, ncmd x 4-byte records, ndict dictionary strings, then the strings in .ofs order,
  contiguous. All strings are packed 12-bit codes (2 codes per 3 bytes), end 0xFFF, byte-aligned (pad nibble 0).
- Codes: < base glyph; 0xFFE newline; 0xFFF end; base+i record i; base+ncmd+k dictionary k (expanded inline
  at load; our rebuilt files have ndict 0). base is per file.
- Records (`ws_window_mess_update_sub` @ 0x41e1e0 switch): 11 speaker name (in pairs around the name, skipped by width calc),
  07 a b ruby (a base glyphs + b reading glyphs follow), 0e choice / 0f branch, 04 string var, 05 number var,
  0c xx button icon (+10 px), 0d xx yy zz pause/voice (sets +0x3cc..), 08 r g b colour, 09/0a speed/wait,
  10 reset style, 00-03 text style.
- Script syntax: see tools/script.py docstring ({name} {ruby:漢字|かな} {choice} {branch} {var} {num} {btn:XX}).

## Hardcoded offset tables — verified in game (2026-11-19)
- `w_sy01` (memory-card check at boot) calls `ws_mess_data_create(file, off)` with 23 offsets compiled in at
  0x5ca788 — it never reads wsy01mes.ofs. Rebuilding wsy01/02 with moved strings hung the boot (black screen after
  the logos). `tools/ofs_tables.py` finds copies of offset runs in the ELF and DLLs: wsy01-05, wmn01 (menus, ~25
  tables), etcmes, mapldmes, btlmes (battle data structs), sgmes/ev1005 (SG002/SG004), wdj01, wki01/04, wsh06, wmp02.
- Hence `script.build_tiled`: strings stay at their offsets; the string area is tiled with dictionary entries
  (the engine walks ndict entries sequentially from the end of the command table) so an overlong translation
  becomes a 3-byte stub [dict ref, END] to a full-text entry appended after the original data. Limits: dictionary
  codes base+ncmd..0xFFD (~1,400 entries), no new command records, 2-byte (empty) slots can't hold a stub.
- 11 files exceed the limit and are relocated (itemdmes, btlmes, mapldmes, rakuzadmes, shopdmes, wki01mes,
  evmndj/evmnng/evryokan, ev0664/ev0666); `tools/ofs_patch.py` rewrites their detected tables (btlmes x6,
  mapldmes x2, wki01 in W_KI01). Items/battle/map/monsters are read through `.ofs` (ItemMessNameGet etc.).
  Risk: tables of < 3 entries are not detected — QA those files' screens.
- Offsets also live in code as `lui rX,hi ; ori/addiu rX,rX,lo` constants (battle messages, the bestiary race
  switch @ 0x1c8838). `ofs_patch.patch_imm` rewrites runs of >= 3 consecutive-string constants anywhere and
  single constants for btlmes >= 4400 in the ELF (verified: bestiary race shows its marker after the fix).

## Font — verified (tests/test_font.py, glyph sheet)
- `font.cmp` (MESARC #0x23F): u16 per glyph, SJIS bytes in order, `00 xx` = ASCII. 2,674 glyphs, no duplicates.
- `font_0000..0003.tex` (MESARC #3-6), `FNTSetRasterUv` @ 0x3b9778: glyph g -> texture g/722, cell (g%722)/2,
  row cell/19, col cell%19, 25x25 px at (col*26, row*26). File = 0x120-byte header + 512x512 4bpp pixels
  (file ends 208 bytes early; that tail is empty). Odd glyphs in bits 0-1, even glyphs in bits 2-3.
  Slots 0xA72-0xB49 (214) are empty.
- Placement: x = column * (26-4 or 26-2) + byte pixel offset; sprite 26x26 (`ws_window_mess_update_sub`),
  2 lines per page; outline drawn as 8 offset copies (`ws_font_draw_chr`).
- Glyph codes 0x00-0x5E = printable ASCII in font.cmp order (space..'_', then 'a'..'~'; no backtick).
  `ws_printf2` (menus, `ws_kana_printf`) already advances codes < 0x60 by a u8 table at 0x783210 (+1; all 12
  originally), other glyphs by size + margin.

## VWF (decisions.md D8) — verified in game (2026-11-19): dialogue, narration, nameplate
- tools/vwf.py redraws codes 0x00-0x5E in PT Serif 19 px (one character per glyph, pen at x=1, baseline 18) and
  writes real advances (+1 px tracking) into the 0x783210 table.
- tools/elfpatch.py makes the other layout code use that table: message window glyph x (window+0x3d2 widened to a
  signed halfword pixel offset), the line-width routine FUN_0041c3b8 (centring), the nameplate, and
  `ws_mess_data_length` (returns ceil(px/22) so ~40 window-sizing callers get glyph-equivalents). Caves in the
  unused ws_debwin_menu_draw after debugpatch's 0x40 bytes. Details in the module docstring.
- English costs one 12-bit code per character (was one per pair): more strings overflow into dictionary stubs.
- Not yet checked in game: ws_printf2 screens (menus), battle windows, event windows sized by ws_mess_data_length.
- #0/#1 font_b/font_s: number fonts (`FNTInitNumFont`). #2 font.tex (452,000 B): not referenced by ws_font_init; unidentified.

## Speaker nameplate — verified in game (2026-11-19)
- `ws_window_mess_start` (0x41d648) copies the `{name}` run into window+0x5c and draws it on a fixed brown plate
  (two objects: +0x38 plain, +0x34 with ruby; `FUN_0041c3b8`'s 2nd output = "has ruby"). Plate ink spans
  x 14-152 of the 640 px frame (~138 px).
- Pitch came from the glyph count (jump table 0x783f70): 1/5/6 -> 22 px, 2 -> 44, 3 -> 33, 4 -> 29, 7+ ->
  uninitialised. `tools/elfpatch.py` (every translated build) forces 22 px, then the VWF cave advances ASCII
  glyphs by their own width; the name stays centred.
- Capacity: ~136 px of English (`vwf.text_width`); longer names overflow into the dialogue text.

## Other archives
- EVENTARC `*.cmp`: compiled event scripts; their SJIS is debug names of script functions, never shown.
  Header: word 2 = offset of an embedded copy of the map's message file (evm*mes, at the module's end: NPCs read
  this copy, tools/evembed.py), words 4-5 = int pool [start, end) holding message offsets (deduplicated, shared
  with script variables; owner modules hold 100% of their file's offsets, others only coincidences).
  Bytecode, classes and the relocation rewrite: tools/evembed.py docstring. Natives (op 0x18) index the table at
  0x5cb1e0: 0-2 BattleFlag Set/Clear/Check, 3-5 PartyFlag Set/Clear/Check, 6-7 PlayerFlag Set/Clear...
- Movie subtitles: AdxMovieSubtitleCreate(window, DATAARC st, MESARC mes, MESARC ofs); `*_st.cmp` = u32 triples
  (start ms, duration ms, string index). The opening (SYSARC #19) had none: tools/opening.py.
- DLL `W_SY05`: SJIS character table (name entry?). Not yet examined.
- Graphics: see docs/re/graphics.md.

## Ghidra
- Project `work/ghidra/namida`, program `SLPM_659.52.analysis` = ELF with lq/sq rewritten to ld/sd (stock MIPS64
  lacks R5900; the EE extension install was blocked), "Non-Returning Functions - Discovered" off.
  Rebuild: see tools/ghidra_scripts (ApplySyms, FixNoReturn, PreOpts). MMI ops (mult rd, etc.) still decode wrong:
  read the disassembly (`$SKILL/scripts/disasm.py dis orig/SLPM_659.52 ADDR N --arch mips --base 0xFF000`).
- 13,374 names from the game's own export table (work/symbols.txt, rebuilt by the scan in the session log).
- `tools/decomp.sh OUT func...`, `tools/xrefs.sh OUT 0xADDR|str:text`, `tools/findref.py 0xADDR`.
- Key: CmpDecompress 0x11ac28, FNTSetRasterUv 0x3b9778, ws_font_init 0x40c7d8, ws_font_draw_chr 0x4108e8,
  ws_mess_data_create 0x410d58, ws_mess_data_length 0x411848, ws_window_mess_update_sub 0x41e1e0,
  EvMesWin* 0x135420.., ItemMess*/BTLDataGetMes*.
