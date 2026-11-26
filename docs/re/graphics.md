# Graphics with Japanese text (survey)

Tools: `tools/txd.py dump FILE.. --out DIR` (RenderWare PS2 native textures inside .crp2/.cmp), `tools/texsheet.py`
(labelled sheets). Sheets of the WINARC survey: `work/qa/gfx/win_0[1-4].png`, `cm*.png` (regenerate with the tools).

## Texture format — 8 bpp verified (readable text in decoded images), 4 bpp partly
- `.crp2` = CMP-compressed custom container: chunk 0x24 (`#define` header), 0x29/0x2a, then RW chunks
  (0x16 TXD, 0x10 clumps). Textures are RW PS2 natives (0x15), rasterFormat 0x2x504 with 80-byte GS upload headers.
- GIF header: A+D TRXPOS @+0x10, TRXREG @+0x20. When TRXREG != width x height the data is swizzled:
  8 bpp sent as PSMCT32 -> `_unswizzle8` (verified). 4 bpp sent as PSMCT32 -> GS memory emulation `_unswizzle4`
  (unverified: no such case seen yet). Most 4 bpp textures are sent as 16-bit (64x16 for 2,048 B) and are
  **not decoded yet** (need PSMCT16 tables): 153 in WINARC, mostly small icons (`wcm99_3xx`, `wic99_00x`, 16x16 ...).
- Palette: 32-bit RGBA, alpha 0..0x80, 8 bpp palette in CSM1 order.
- Re-insertion: `tools/gfx.py` (8 bpp only) maps edited pixels to the texture's own palette, writes them back through
  the `_unswizzle8` address map and recompresses the .crp2; build.py rebuilds WINARC from its `EDITS` table.
  `gfx.py preview DIR` decodes what it wrote. Verified in game 2026-11-22: title menu wti99_112 "New Game" /
  "Continue" (PT Serif Bold 26 px, cream with brown edge; the game's own selection tint still applies).

## WINARC (window graphics) — surveyed 2026-11-19, 1,260 textures decoded
| Group | Files | Japanese text |
|---|---|---|
| Common window `cm.crp2` | wcm99_*, wba99_* | yes: status labels (体(最大) 技(最大) 攻撃力 ... 運, 変化/装備/基本), 奥義, 攻撃/回復/補助 tabs, 持っている数, 攻撃回数, 打 |
| Item/weapon/armour/accessory menus `ki01-ki08` | wki99_* | yes: headers (魔物 防具 飾り 道具 武器図鑑 魔物図鑑), columns (持っている数 分解 属性 材料 水/名水/神水 レシピ 装備), 競売 (auction) labels, ナミダ通信 newsletter header, 全記事数/発行時間, 新 badge |
| Shops `sh01-sh07` | wsh99_* | yes: 買う 売る やめる, 手数料, 掲示板, 依頼内容, 物々交換, 鑑定/鑑定料, 宿泊と記録 ... |
| Data/encyclopedia `de02-04` | wde99_* | yes: 属性 装備 防御力 攻撃力 攻撃回数 回復 攻撃 補助 |
| Music player `dj01` | wdj99_000 | yes: 曲を聴く etc. |
| Map `mp01/02` | wmp99_* | yes: 拡大/縮小, 現在地 |
| Mini-game `sg01` | wsg99_190 | yes: 最大たる破壊数, 勝利数/挑戦数, 最大連鎖数 勝率, 一番..九番 |
| Mini-game digits `mnsj` | wsg99_80x | no (digits, buttons) |
| Title `ti` | wti99_100-143 | logo 天外魔境 (keep, already has "NAMIDA FAR EAST OF EDEN"); wti99_112: PRESS START BUTTON + 最初からはじめる / 続きからはじめる |
| Town title cards `tn01` | wtn01_* (24) | yes: town names (宇佐町 別府町 博多町 太宰府 長崎町 熊本町 金毘羅町 鬼ヶ城 鹿児島町 宮崎町 竜宮城 ...) + kana readings; dungeon banners (変化城 魅惑城 雷城 地底城 天空城 マダラ城 黄金神殿 ...) |
| Staff roll `staff` | daishi_00..06, staff_88-99 | yes: brush calligraphy (天外魔境アリ, 自在所ヲ知ル ...) — decide with user (credits/art) |
| Save/system `sy05` | wsy99_500 | yes: 消す, 入力 (name entry keys?) |
| Newsletter art `wki98_*` (92) | | no text seen |
| Item art `wcm90-96` (894) | | not reviewed one by one; spot checks show art only |

## Battle (surveyed 2026-11-24; gfx/labels_battle.json, gfx.py "archive" key)
- WINARC wba99_704: hit-counter digits + 打 (x 464-512) -> "Hits". BTLARC number.crp2 BSYS00_001 技 -> "TP".
- EFFARC (1,595 textures, work/gfx/EFFARC; index work/qa/ub/effth_index.txt): ee001_00 ミス! -> "Miss!",
  ee000_00 / ed099_04 無効 -> "Immune", ed047_00 全 -> "All". The cyan/yellow glyph sheets (ef096/ef097, ej000,
  em0a*_eff_moji) are an invented rune script, not Japanese.
- Spell/technique sigils (D25, gfx/labels_sigils.json, gfx.draw_sigil): glowing brush kanji stacked over the
  caster for ~1 s; now the English name sideways down the same column (Flame verified in game). ef000/002/004 妖火/烈火/天火, ef006/008/010 water, ef012/014/016
  thunder, ef018/020/022 wind, ef023-026 ice, ef050-068 力/堅/速 (Power/Guard/Speed up/down), ef086 白仙, ef088,
  ef090 光陣, ef092 鳴動, ef098 馬/鹿/超.

## Not surveyed yet
SYSARC (522 MB), SGARC (mini-games), WORLDARC, CHARAARC, DATAARC, MOVIEARC (FMV: subtitles?),
and the 153 undecoded 4 bpp textures.
