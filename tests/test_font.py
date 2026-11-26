"""Font textures and the variable-width English font."""
import os, sys, struct
import pytest
from conftest import need_iso, ROOT
sys.path.insert(0, ROOT)
import unpack, script, afs, font as fontmod
import vwf
from cmp import decompress


@pytest.fixture(scope='module')
def mes():
    need_iso()
    return unpack.unpack(verify=False)


def test_texture_roundtrip(mes):
    for p in fontmod.tex_paths(mes[1]):
        d, img = fontmod.load_tex(p)
        assert fontmod.save_tex(d, img) == d


def test_glyph_layout_matches_table(mes):
    """Glyph 0x21 is 'A' in font.cmp and must have ink; slot 0xa72 (first unused) must be empty."""
    texs = [fontmod.load_tex(p)[1] for p in fontmod.tex_paths(mes[1])]
    font, _ = script.load_mesarc(mes[1])
    assert font[0x21] == 'A' and fontmod.get_glyph(texs, 0x21).sum() > 50
    assert fontmod.get_glyph(texs, 0x0).sum() == 0          # space
    assert fontmod.get_glyph(texs, 0xa72).sum() == 0


def test_vwf_encoding_and_widths(mes):
    """English encodes to the game's ASCII glyph codes; every one has a sane advance and fits its cell."""
    font, _ = script.load_mesarc(mes[1])
    enc = script.Encoder(font); cmds = []
    codes = enc.encode('{name}Tengu{name}Hi there\nok{var}!', 0xA72, cmds)
    assert all(c < 0x5F for c in codes if c < 0xA72) and codes.count(script.NL) == 1
    assert cmds == [b'\x11\0\0\0', b'\x04\0\0\0']
    vf = vwf.VwfFont(); t = vwf.width_table(vf, font)
    assert len(t) == 0x60 and t[font.index(' ')] + 1 >= 4
    assert t[font.index('i')] < t[font.index('m')] < 24
    for g, ch in vwf.glyph_set(font):
        a = vf.render(ch)
        assert a.shape == (25, 25) and (ch == ' ' or a.max() >= 2)


def test_marker_build_decodes(mes):
    import build
    od, md = mes
    arc, n = build.build_mesarc(od, md, marker=True)
    assert n == 637
    tmp = os.path.join(ROOT, 'work', 'test_marker.afs'); open(tmp, 'wb').write(arc)
    a = afs.Afs(tmp)
    raw = decompress(a.data(a.index('ev0201mes.cmp')))
    offs = list(struct.unpack('<16I', a.data(a.index('ev0201mes.ofs'))))
    md2 = script.MdFile(raw, offs)
    assert len(md2.strings) == 16 and md2.strings[0][-1] != script.END
    os.remove(tmp)
