# Debug tool: scene list

How to reach each scene from a cold boot of a `--debug` build (`tools/pcsx2.py run ISO --route R --out DIR`).
`warp REGION` (at the title menu, before New Game) sets the party region/area via PINE and skips the opening
movie (debugpatch SKIP mailbox); region ids and names: `tools/debug/regions.tsv`. No story flags are set: a warp
lands in free roam with a level-1 party.

| Scene | Route | Status | Proof shot |
|---|---|---|---|
| Title menu | routes/title.txt | ok | work/qa/warp/title.png |
| Opening narration + first dialogue | routes/newgame.txt (~5 min, plays the movie) | ok | work/qa/vwf/zoom_dialog.png |
| Town street (region 0x1f1, 北町) | routes/warp_test.txt (~2 min) | ok | work/qa/warp/a.png |
| Field menu (Triangle) | routes/menu_probe.txt (from slot 2 = warp_test) | ok | work/qa/menu/tri.png |
| Lost Forest (0x0f3) | routes/battle_probe.txt | arrives; no random encounter (no trigger zones without story flags) | work/qa/battle/arrive.png |
| Battle | routes/battle.txt (~2.5 min): `battle N` in the field forces formation N (debugpatch ENC hook) | ok, slot 4 = command menu | work/qa/battle/battle2.png, cmd.png |
| Shop, save screen, map, every DLL screen | routes/window_probe.txt (~2 min; saves slot 5 = town street) then routes/window_survey.txt (all kinds from slot 5) | ok, see below | work/qa/win/sheet.png, work/qa/winsurvey/s1-s3.png |
| Later story scenes | `flag N` / `unflag N` (party flags), `event CLASS METHOD` | open: needs the event VM (see below) | |

## Story scenes: what's known

- Party flags: flag n = bit n&31 of the u32 at 0x793600 + (n>>5)*4 (_FlagSet @ 0x13bba8). Route `flag N`/`unflag N`.
  A fresh New Game + warp to 0x1f1 has 15 set: 0x38c 0x38e 0x391 0x3c2 0x3cb 0x44b 0x497 0x4cd 0xaf1 0xaf2 0xb30
  0xb32 0x101f 0x11c1 0x1d68. Field menu: 地図 needs flag 0x53, 記録 needs SystemFlag 2 (save spots).
- Event scripts are per map: EVENTARC holds 228 modules (writers' files + one per map, e.g. 0148_mnng_p for the
  0x1f1 street). Loaded modules: list at 0x7932e8 (3 in town: 0x350001 evfunc, 0x350002 evsub, the map's).
  Classes are story events (`ev0500`..), NPCs (`nn2200`..: 初期化/削除/イベント) and helpers; methods are SJIS names.
  The class/method list of a loaded module: scratch tool evclasses.py → work/evclasses_1f1.txt.
- Every class in the map module already exists as an idle process when the map loads (process list 0x7932f0);
  scenes start from their フレーム/初期化 methods when flags match. `event CLASS METHOD` (debugpatch, calls
  0x132c98 = Ev_ProcessCreate + EV_MethodCall) creates a new process but nothing shows: tried ev0503/ev0658
  デバッグ and イベント, nn2200/nn2201 イベント, ev1005_闇賭博 説明. デバッグ sets no party flags.
- Next step if scenes are needed: decode the event bytecode (process pc at +0x10, VM in 0x11b000-0x11c000 and
  the ev_* natives @ 0x423000+) to read which flags each evNNNN checks, then `flag` them and re-enter the map.

## DLL screens: `window KIND ARG`

`window KIND ARG` (field, free roam) calls EvWindowCall(KIND, ARG, 0), as NPC scripts do. ARG is the shop number for
the shop kinds (1 used throughout; shop 1's goods are 4 items). Cross backed out of the shop, save screen and map cleanly (the survey reloads slot 5 instead of exiting). The field menu's
記録 is greyed without story flags; `window 0xe` reaches the save screen anyway (writes go to the repo's own memory card).

| Kind | DLL | Screen | Notes from the marker build |
|---|---|---|---|
| 0 | w_sh01 | shop: 買う/売る/やめる, goods list, 持っている数 | tabs, 価格 header are textures |
| 1 | w_sh02 | 飾り生成 (accessory crafting): 自分で/レシピから/見る, 手数料 | |
| 2 | w_sh03 | 掲示板 (bulletin board) | |
| 3 | w_sh04 | 物々交換 (barter): ください/あげます | slot labels are textures |
| 4 | w_sh05 | 鑑定 (appraisal) | |
| 5 | w_sh06 | inn: 宿泊と記録 / 宿泊 / 記録, 一泊 777両 | sets the 0x389 flags when a stay is taken |
| 6 | w_sh07 | 交換札 exchange (item list, 持ち札) | |
| 7 | w_ki01 | newspaper: 最新の記事/全ての記事/未読の記事 | |
| 8-0xd | w_ki02-06, 08 | encyclopedias: 魔物図鑑, 武器図鑑, 防具, 飾り, 競売 (auction), 道具 | headers are textures |
| 0xe | w_sy02 | 記録 save screen, slots 01-03, confirm dialog (wsy02:51/52) | |
| 0xf | w_sy05 | name entry: kana grid + face | needs an English letter grid; tab markers overflow |
| 0x10 | w_ms02 | message/choice window | |
| 0x11 | w_sg01 | 攻略時間 (clear times, 一番-十番) | all textures |
| 0x12 | w_dj01_01 | 捨てる/壊す list with prices | |
| 0x13 | w_dj01_04 | 曲を聴く (music player), 一曲 5両 | long lines clip at the box's right edge |
| 0x14 | w_mp01 | world map, 拡大/縮小, 現在地 | |
