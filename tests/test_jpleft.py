"""No kana/kanji left in any message string the built disc can show (tools/jpleft.py: MESARC + map-embedded copies)."""
import os, pytest
from conftest import need_iso, ROOT
import jpleft

ISO = os.path.join(ROOT, 'build', 'namida_en.iso')


def test_no_japanese_left_in_messages():
    need_iso()
    if not os.path.isfile(ISO): pytest.skip('no build/namida_en.iso')
    hits = jpleft.scan(ISO)
    assert not hits, f'{len(hits)} strings still Japanese, first: {hits[:5]}'
