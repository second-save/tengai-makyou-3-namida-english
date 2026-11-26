#!/usr/bin/env python3
"""Generates gfx/labels_sg.json: mini-game graphics (SGARC sg001-sg004) in English.

Entries with "clump" are drawn through the window model (tools/gfx.py draw_mesh; screen boxes in model units, y up,
from tools/rwgeo.py); the others are plain texel boxes (draw_label). sg001 = Hundred Cuts brawl, sg002 = Yami dice
(chou-han), sg003 = mask-whacking, sg004 = rotating-tile cave puzzle.
"""
import json, os

BROWN, CREAM, RED = [104, 58, 22], [252, 244, 214], [190, 30, 30]
L = []


def mesh(member, clump, tex, items, **kw):
    L.append(dict(archive='SGARC', member=member + '.crp2', clump=clump, tex=tex,
                  items=[dict(box=b, text=t) for b, t in items], **kw))


def box(member, tex, b, text, **kw):
    L.append(dict(archive='SGARC', member=member + '.crp2', tex=tex, box=b, text=text, **kw))


banner = dict(fill=BROWN, edge=CREAM, stroke=3)
white = dict(fill=[255, 255, 255], edge=[255, 255, 255], stroke=3)        # glow copies drawn under the banners
for m, c in (('sg001', 10), ('sg003', 16), ('sg004', 92)):
    mesh(m, c, 'wsg99_112', [([0, -40, 242, 40], 'Start!')], layout='row', note='開始!', **banner)
for m, c in (('sg001', 11), ('sg003', 17)):
    mesh(m, c, 'wsg99_111', [([0, -40, 186, 40], 'Finish')], layout='row', note='終了', **banner)
mesh('sg004', 94, 'wsg99_400', [([0, -41, 248, 41], 'Success!')], layout='row', geo=[1, 2, 3], note='成功!', **banner)
mesh('sg004', 94, 'wsg99_404', [([0, -41, 248, 41], 'Success!')], layout='row', geo=[4, 5, 6], note='成功! glow', **white)
mesh('sg004', 93, 'wsg99_401', [([0, -39, 197, 39], 'Failed')], layout='row', note='失敗', **banner)
# 百斬く! (100 cuts): pieces centred at 0, layout unseen in game, so each piece gets a whole word of its own
for tex, geos, style in (('wsg99_115', (1, 2, 3, 4), banner), ('wsg99_119', (5, 6, 7, 8), white)):
    for g, b, t in zip(geos, ([-48, -41, 49, 41], [-45, -25, 45, 25], [-51, -42, 52, 42], [-27, -39, 27, 40]),
                       ('100', ' ', 'Cuts', '!')):
        mesh('sg001', 12, tex, [(b, t)], geo=[g], note='百斬く! piece', **style)
mesh('sg001', 13, 'wsg99_110', [([-50, -23, 50, 23], 'Combo!')], note='連鎖!', **banner)
mesh('sg001', 19, 'wsg99_114', [([-96, -21, 96, 21], 'New Record!')], note='記録更新!', fill=RED, edge=CREAM, stroke=3)
mesh('sg001', 20, 'wsg99_113', [([-85, -18, 86, 19], 'Clear Time')], note='攻略時間', **banner)
mesh('sg002', 17, 'wsg99_200', [([-75, -19, 75, 19], 'Win Streak!')], note='連勝中!', fill=RED, edge=CREAM, stroke=3)
# pause dialogs (brown text on the parchment window, no outline)
dlg = dict(fill=[92, 52, 20], edge=[92, 52, 20], stroke=0)
mesh('sg001', 17, 'wsg99_121', [([-90, 34, 88, 58], 'Resume'), ([-90, -12, 88, 12], 'Restart'),
                                ([-90, -58, 88, -34], 'Quit')], note='ゲームを再開する / 始めからやり直す / ゲームをやめる', **dlg)
mesh('sg001', 15, 'wsg99_122', [([-134, 28, 128, 52], 'Quit this game'), ([-134, -2, 128, 22], 'and start over?')],
     note='このゲームを終了して始めからやり直しますか?', **dlg)
mesh('sg001', 18, 'wsg99_122', [([-97, -52, -27, -28], 'Yes'), ([24, -52, 94, -28], 'No')], texels=[0, 48, 140, 64],
     note='はい / いいえ', **dlg)
mesh('sg001', 16, 'wsg99_123', [([-121, 28, 117, 52], 'Do you really want'), ([-121, -2, 117, 22], 'to quit this game?')],
     note='本当にこのゲームを終了してもいいですか?', **dlg)
mesh('sg004', 96, 'wsg99_402', [([-121, 13, 117, 37], 'Quit the game?'), ([-97, -37, -27, -13], 'Yes'),
                                ([24, -37, 94, -13], 'No')], note='終了してもいいですか? はい いいえ', **dlg)

# score bars: texel rows map 1:1 to the screen (rwgeo: row0 -> x -320..-64, row1 -> -64..192, row2 -> 192..320)
bar = dict(fill=[255, 236, 170], edge=[80, 45, 15], stroke=2)
box('sg003', 'wsg99_300', [36, 2, 126, 35], 'Time', bg='tile 140 180', **bar)            # 時間
box('sg003', 'wsg99_300', [218, 39, 250, 72], 'pts', bg='tile 180 214 37', **bar)       # 点 (after the number)
box('sg003', 'wsg99_300', [2, 76, 96, 109], 'Score', bg='tile 100 126 74', **bar)       # 得点
box('sg004', 'wsg99_403', [76, 2, 144, 35], 'Left', bg='tile 150 190', **bar)            # 残り
box('sg004', 'wsg99_403', [192, 2, 236, 35], 'steps', bg='tile 150 190', **bar)          # 歩 (after the number)
box('sg004', 'wsg99_403', [70, 39, 124, 72], 'Keys', bg='tile 130 170 37', **bar)       # 鍵
box('sg004', 'wsg99_403', [234, 39, 256, 72], ' ', bg='tile 196 226 37', **bar)         # 個 (counter word: dropped)
box('sg001', 'wsg99_116', [0, 0, 50, 32], 'HP', bg='clear', fill=CREAM, edge=[60, 35, 15], stroke=2)   # 体力
box('sg001', 'wsg99_102', [58, 60, 128, 104], 'Cuts', bg='solid', fill=CREAM, edge=[60, 35, 15], stroke=2)  # 人斬

# dice game plates
plate = dict(fill=CREAM, edge=[70, 40, 15], stroke=2)
box('sg002', 'wsg99_201', [26, 6, 122, 34], 'Chips', bg='solid', **plate)              # 持ち札
box('sg002', 'wsg99_205', [26, 6, 122, 34], 'Bet', bg='solid', **plate)                # 賭け札
for t in ('wsg99_201', 'wsg99_205'):
    box('sg002', t, [84, 46, 122, 76], ' ', bg='tile 30 60')                            # 枚 (counter word)
box('sg002', 'wsg99_202', [52, 4, 104, 52], ' ', bg='tile 6 40')                        # 枚
box('sg002', 'wsg99_207', [0, 96, 42, 128], 'x', bg='clear', fill=CREAM, edge=[60, 35, 15], stroke=2)  # 倍 (odds)
box('sg002', 'wsg99_203', [18, 18, 110, 106], 'EVEN', bg='solid', fill=RED, edge=[110, 20, 20], stroke=1)  # 丁
box('sg002', 'wsg99_204', [14, 18, 108, 104], 'ODD', bg='solid', fill=CREAM, edge=[120, 20, 20], stroke=1)  # 半

# brawl barrels: 薬 heal, 火 fire, 力 power
for t in ('sb01_t1', 'sb001_taru_yaku'):
    box('sg001', t, [66, 6, 122, 58], 'Heal', bg='disc 94 32 27 35 80 61', fill=CREAM, edge=[20, 70, 60], stroke=1)
box('sg001', 'sb01_t2', [66, 4, 124, 58], 'Fire', bg='solid', fill=CREAM, edge=[90, 20, 10], stroke=1)
box('sg001', 'sb01_t3', [62, 14, 120, 66], 'Power', bg='poly 90 1 127 40 90 78 53 40', fill=CREAM, edge=[90, 70, 10], stroke=1)

# cave puzzle tiles: kanji numerals 一..九 -> digits (three tile sets)
for s in (1, 2, 3):
    for n in range(1, 10):
        box('sg004', f'sg004_m{s}w{n}', [28, 30, 66, 68], str(n), bg='disc 46 46 22 217 176 102', fill=[60, 35, 15],
            edge=[60, 35, 15], stroke=0)

json.dump(L, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'labels_sg.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(len(L), 'labels')
