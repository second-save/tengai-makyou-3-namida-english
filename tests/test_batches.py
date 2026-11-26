"""Translation batch checks (tools/batches.py): tags, font, glossary, width; and the shipped English passes them."""
import sys
from conftest import ROOT
sys.path.insert(0, ROOT + '/tools')
import batches


def entry(jp, file='ev0100mes'):
    row = {'id': 0, 'jp': jp, 'en': ''}
    return dict(file=file, rows=[row], i=0, jp=jp, en='', box='dialogue', speaker='', reading=False)


TERMS = [(['壱与'], ['Ichiyo'], ['Iyo']), (['壱与の母'], ['Mother'], [])]


def test_problems():
    e = entry('{name}村人{name}{ruby:壱与|いちよ}が{var}を\n持ってきた')
    assert batches.problems(e, '{name}Villager{name}Ichiyo brought {var}.', TERMS) == []
    p = lambda en: ' | '.join(batches.problems(e, en, TERMS))
    assert 'tags differ' in p('{name}Villager{name}Ichiyo brought it.')              # {var} dropped
    assert 'glossary: 壱与' in p('{name}Villager{name}She brought {var}.')
    assert 'Avoid: Iyo' in p('{name}Villager{name}Ichiyo (Iyo) brought {var}.')
    assert batches.problems(entry('{var}を持ってきた'), 'Iyo brought {var}.', TERMS) == []  # Avoid only with the JP term
    assert 'font lacks' in p('{name}Villager{name}Ichiyo brought {var}。')
    assert 'ordinal' in p('{name}Villager{name}Ichiyo brought the {var}th.')
    assert '440' in p('{name}Villager{name}Ichiyo brought {var}' + ' and more' * 10)


def test_unmeasured_box_uses_the_japanese_size():
    e = dict(entry('攻撃を３回'), box=None)                      # 5 glyphs = 110 px, 1 line
    assert batches.problems(e, 'Hits 3x', []) == []
    assert any('px >' in p for p in batches.problems(e, 'Attacks three times in a row', []))
    assert any('lines >' in p for p in batches.problems(e, 'Hits\n3x', []))


def test_longer_term_wins():
    e = entry('{name}壱与の母{name}おかえり')
    assert batches.problems(e, '{name}Mother{name}Welcome home.', TERMS) == []


def test_shipped_english_passes():
    assert batches.main(['check']) == 0
