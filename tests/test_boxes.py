"""Width gate: every translated line fits its measured box (tools/boxes.py, docs/windows.md)."""
import sys
from conftest import ROOT
sys.path.insert(0, ROOT + '/tools')
import boxes


def test_translations_fit_their_boxes():
    probs = [p for name, rows in boxes.load_all() for p in boxes.check(name, rows)]
    assert not probs, '\n'.join('  '.join(map(str, p)) for p in probs[:40])


def test_lint_catches_overflow():
    rows = [{'id': 0, 'jp': '{name}村人{name}あ', 'en': '{name}Villager{name}' + 'W' * 30},
            {'id': 1, 'jp': '{name}村人{name}あ', 'en': '{name}' + 'M' * 12 + '{name}Hi.'},
            {'id': 2, 'jp': 'あ', 'en': 'Fine.\nAlso fine.'}]
    probs = boxes.check('ev0100mes', rows)
    assert [(p[1], p[2]) for p in probs] == [(0, 'dialogue'), (1, 'nameplate')]


def test_choice_options_use_the_choice_panel():
    long_opt = 'M' * 25                       # 425 px: fits dialogue (440), not the choice panel (400)
    rows = [{'id': 0, 'jp': '{name}村人{name}どれ？\n{choice}\nはい\nいいえ\n{branch}\nそうか',
             'en': '{name}Villager{name}Which?\n{choice}\n' + long_opt + '\nNo\n{branch}\n' + long_opt}]
    probs = boxes.check('ev0100mes', rows)
    assert [(p[2], p[3].split(':')[0]) for p in probs] == [('choice', 'line 3')]


def test_item_records_classified():
    rows = [{'id': i, 'jp': t} for i, t in enumerate(['シイタケのおにぎり', 'しいたけのおにぎり', '体を回復', 'a\nb\nc'])]
    assert boxes.classify('itemdmes', rows) == ['item_name', 'item_kana', 'item_desc', 'item_lore']
