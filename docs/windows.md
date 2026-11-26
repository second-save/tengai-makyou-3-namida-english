# Window data: text budgets per box (width gate)

Budgets are VWF pixels (`vwf.text_width`, game px = screenshot px horizontally; verified: 40 digits = 440 px drew
x 163-602). Measured with ruler strings (`build.py --qa-file tools/debug/width1.tsv`, digits are 11 px each)
and the routes named below. Status: **measured** (shot named) or **guess** (measure before translating).

How to measure: put a ruler in the string (`--qa-file`), reach the box (tools/debug/scenes.md), read the first and
last x where the box can hold text in a 2x zoom of the shot. Item/list fields: budget = x of the next column's
widest content minus the field's x, minus a 4-6 px gap.

| Box | Strings | Budget | Lines | Status / shot | Notes |
|---|---|---|---|---|---|
| Dialogue with nameplate | ev*mes, wms02 prose | 440 px per line | 2 per page | measured: work/qa/width/q_b/q1.png, q2.png | text x = 163. No clipping: line 1 ran to the screen edge (x 640); the ▽ sits on line 2's row at x 611-623, so line 2 must end by ~605. 440 = the Japanese max (20 glyphs x 22). A 3rd line goes to the next page. |
| Nameplate | `{name}..{name}` | ~136 px | 1 | measured: q_a/q1.png | Fixed box x 12-154. 7 M (119 px) fits; 10 M (170 px) overflows to the left (centred). |
| Choice prompt line | the line before `{choice}` (wms02:1) | as dialogue (440 px)? | 1 | q_c/p2.png | no character cap: 70 characters drew to the screen edge (tour2/quiz3.png only caught the typewriter mid-line). The choice list itself is not measured yet (the quiz times out first; find an event choice). |
| Field menu location | mapld region + wmn01:63 `{var}／{var}／{var}` | ~335 px for the composed line | 1 | measured: tour2/menu1.png | x 23 to the box edge at ~362; parts are joined at runtime, so the longest region+area+spot combination counts. |
| Top help line | wsh01:0, wmn01:45 (screen help) | ~600 px | 1 | measured: tour2/shop1.png, menu1.png | runs to the screen edge; keep inside overscan (~x 610). |
| Shop goods list: item name | itemd names | ~230 px | 1 | measured: tour2/shop1.png | name x 53; prices right-aligned to x 350 in the JP font (~12 px/digit, up to 5 digits). |
| Items menu (持物) list: item name | itemd names | ~210 px | 1 | measured: tour2/menu2.png | name x 68; count right-aligned at x ~297 (2 digits); text is clipped at the column divider x ~314 (tour3/items.png: 22 of 40 digits shown). Smallest item-name budget so far. |
| Item one-line description | itemd, 3rd string of each item | ~590 px | 1 | measured: tour2/shop2.png | the shop's top help bar (x 16 to the screen edge); keep inside overscan. |
| Item lore (details page, Square in a shop) | itemd, 4th string (3-4 lines) | ~290 px per line | 4 | measured: tour3/z_lore.png | text x 14; the 分解 button starts at x ~312 on line 1, a label sits right of lines 3-4 from x ~388. JP max 12 glyphs (264 px). Also check the encyclopedia layout. |
| Item kana reading | itemd, 2nd string (しいたけのおにぎり) | ~230 px | 1 | measured: tour3/z_lore.png, tour2/shop2.png | **shown**: right part of the details-page bar and the shop's top-right. Probably the sort key too: decide what English puts there (name again?). |
| Item name, details page | itemd names | ~500 px | 1 | measured: tour3/z_lore.png | x 52 to the ornament at ~560; the list budgets above are smaller. |
| Yes/no confirm box (save) | wsy02:51/52 prompt, wsy02:0/1 options | prompt ~415 px/line, 2 lines; options ~110 px (left) / ~90 px (right) | 2 + options | measured: work/qa/width/save/s2.png (rulers: tools/debug/width3.tsv, route width_save.txt) | box x 96-548, prompt text x 110 (frame ~530). Options left-aligned at x 220 and 345; the cursor highlight is ~98 px wide. |
| Shop name (bottom bar) | shopd names | ~380 px | 1 | measured: work/qa/width/z_shopd.png | x 24 up to the 所持金 label at ~410. |
| Battle item list | itemd names / descriptions | as the items menu (210 / 590) | 1 | work/qa/width/bitems/items.png | same two-column list (name x 68, count ~297), description in the top bar, kana top right; the used item's name shows in the top bar. |
| Bestiary list (魔物図鑑) | btl monster names | ~230 px | 1 | measured: work/qa/width/wbest/p2.png | x 30 to the list box edge ~262; not clipped. |
| Bestiary lore (page 2) | btl monster lore | ~320 px | 6 | measured: wbest/z_p2.png | x 308 to the panel edge; a 7th line overlaps the 種族 row. JP max 6 lines. |
| Bestiary strengths / weaknesses | btl, 5th/6th string of a monster | ~275 px | 2 | measured: wbest/z_p2.png | x 352. |
| Bestiary location (page 4) | btl, 4th string (国／地域) | ~390 px, maybe 36 characters | 1 | measured: wbest/z_p4.png | the 60-digit ruler stopped after exactly 36 characters with room left: a character cap or a clip; retest with narrow letters. |
| Choice panel option | lines after `{choice}` (ev*, wms02 options) | ~400 px | 1 per option | measured: work/qa/width/qchoice2/z.png (tools/debug/width5.tsv, route quiz_choice.txt) | fixed panel from x ~197 to the screen edge, option text x ~219 (the selected row shifts left to ~190); 36 digits (396 px) fit. Up to 6 options seen. Lint: boxes.option_lines. |
| Battle action banner | technique / command names (btl 4428 攻撃, skill names) | ~300 px | 1 | measured: work/qa/width/wbattle/z_banner.png (width6.tsv, route width_battle.txt) | text x ~315 beside Namida, runs to the screen edge unclipped. |
| Rank-up new skills (新規技能 / 新規奥義) | technique and 奥義 names | ~185 px | 1 per skill | measured: wbattle/z_newsk.png | box x ~20-208; longer names spill out of the frame (not clipped). Tightest place skill names appear: lint budget for all 322 skill names. |
| 設定 (settings) | wmn01:162-185 | labels ~140 px; left options ~95, right ~120; 速/遅 ~25 | 1 | measured: work/qa/width/settings/set2.png (tools/debug/width7.tsv), JP layout work/qa/width/sk_jp/z2.png | rows x 100-537, label x 112, options at fixed x (~252/295 and ~398); text is not clipped and overlaps the next column. 速/遅 flank the 1-5 speed digits: one short word or arrows. Help lines (163, 165...) use the top bar. |
| Field menu location (composed) | mapld names joined as 国／地域／場所 | ~335 px total | 1 | measured: work/qa/width/jpref/zmenu.png, rtour/menu.png | Per-name lint uses a placeholder (264, JP max) until the region -> (country, area, spot) mapping is known: then check the composed line. |
| Map screen labels | mapld country name + its reading; current-location label + reading | ~95 px (name), ~170 px (right box) | 2 | measured: work/qa/width/jpref/map.png | **readings are shown** (ながさき under 長崎): English needs something there (blank, or a subtitle). |
| Music list (曲を聴く) | wdj01_04 song titles | ~440 px | 1 | measured: work/qa/width/rtour/z19.png | list x ~90 to the scroll bar ~540. |
| Discard/break list (捨てる/壊す) | wdj01_01 building kinds | ~220 px | 1 | measured: rtour/z18.png | text x ~170, price right-aligned to ~460. |
| Encyclopedias (図鑑: weapons, armour, accessories, items) | itemd names / descriptions / lore | as items (210 list, lore ~290 x 4) | | measured: rtour/s3.png | same list + right panel as the shop details page; lore lines from x ~330. |
| Battle top bar | item / command help (itemd, etc, btl) | ~600 px | 1 | rtour, btext | same bar as the field help (590 budget). |
| Bulletin board (rakuzad), newspaper (wki01), staff credits | rakuzad, wki01, staff | not reachable | | rtour k2/k7 (empty lists) | the board and newspaper are empty without story progress; staffmes is the ending roll. Need story flags or a way to unlock entries (wki01 read flags, rakuzad post flags). |
| 技能 equip list, technique/奥義 descriptions | btl technique records | not reachable | | work/qa/width/skp2 | the slot list opens nothing even in the unmodified JP build at 18段 with learned + mastered techniques: another condition (scrolls 巻物? 伝授?) gates it. |
| Battle target bar | btl monster names | ~580 px | 1 | measured: tour3/z_bt.png | top bar, x 18; names also appear in other battle windows: check those. |
| Narration (no window, centred) | ev*mes without `{name}` (ev0100:0-8) | ~540 px | 2 per page | measured: work/qa/width/opening (f005586 etc.) | centred on x 320, no box: 50 digits (550 px) drew x 44-596, 60 digits ran off both edges. 540 keeps ~50 px margins for overscan. ▽ at the right, typewriter reveal. |
| Area name banner (on entering an area) | mapld names | guess | vertical | opening f010621 | **drawn vertically**, one glyph per row, top right: English needs engine work (horizontal banner) or a short name. |
| Battle messages, item/skill lists, encyclopedias, bulletin board, inn, crafting | btl, itemd, wki*, wsh* | guess | | | window_survey.txt reaches the screens |

Engine hazards found while measuring:
- **DLL screens and file size:** the quiz window (w_ms02) does not open once wms02mes.cmp passes 2048 bytes
  compressed (one sector; the original is 1367): every failing build was >= 2049 B, every working one <= 2036 B,
  whatever the line lengths or counts. Mechanism not found (not the per-string decoder, which sizes dynamically).
  Event files are not limited: ev0100mes went from 1 to 2 sectors (3730 B) and its long strings displayed.
  **2026-11-21: not a general limit.** Every MESARC read sizes itself from the AFS: `_AdxRead` (0x108430) opens
  the member with ADXF_OpenAfs, takes ADXF_GetFsizeSct, allocates sectors x 2048 and decompresses into
  CmpGetOrgSize bytes; the DLLs (W_KI01: AdxFileEntry/AdxFileEntryWait, size argument 0) and w_mn01 (0x277, size 0)
  pass no sector counts. wki01mes in English (55.7 KB, 28 sectors vs 21) opens, lists headlines and shows early
  and late articles (route tools/routes/newspaper.txt pokes the news list at 0x795fb2; shots work/qa/news_art).
  2026-11-22: wms02mes padded to 2,353 B (2 sectors) opened and displayed (route quiz_cold.txt, work/qa/quiz_big):
  the old failure was not the size. build.py has no sector guard any more. Cold-boot routes stalled twice on the logos while the disk was
  98% full: free space before blaming a build.
- **Relocated btlmes, fixed:** battle code builds message offsets as `lui`/`ori` constants (switches such as
  the bestiary race names at 0x1c8860, status-cure and battle messages in BTLCheckAtkPlayer, SpReEntrySpKindEff,
  BTLWin*). The relocated btlmes broke them all (the race showed garbled kanji). tools/ofs_patch.py patch_imm
  now rewrites runs of >= 3 such constants in any file and single ones for btlmes strings >= 4400 (152 sites;
  the low half is often in a jal delay slot 4 instructions after the lui: window 8, stops at a write to the
  register). The action banner showed `玄城壁[btl:1680]` instead of 攻撃 until the window was widened.
  Other relocated files have a few single matches (itemd 24, mapld/shopd 7, staff 4), mostly coincidences in
  RenderWare or DLL code: unpatched; QA their screens.
- Event dialogue strings have no practical length cap: 10 lines x 45 characters paged through fine (long_ev).
- The 9-M nameplate filled the box edge to edge; nothing crashed at 13 M (ev0100:9 / ev0500 rulers).

Glyph torture line (tools/debug/torture.tsv, route width_opening.txt): every ASCII glyph, double spaces, quotes and
apostrophes render in narration and dialogue (work/qa/width/torture/z1-z3.png). Fixed on the way: stray bars above
^ | ~ and their neighbours came from the original glyphs' ink in the gap row above each cell, which the game samples;
font.put_glyph now clears that row.
- Overriding a relocated file (itemd, ...) patches the ELF, so savestates from other builds don't load:
  width_tour.txt cold-boots and saves its own slot 6.
