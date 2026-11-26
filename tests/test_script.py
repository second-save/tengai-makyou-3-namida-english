"""Script extraction: every string re-encodes to the game's own codes; rebuilt files parse back."""
import struct
import pytest
from conftest import need_iso
import unpack, script
from cmp import decompress


@pytest.fixture(scope='module')
def mesarc():
    need_iso()
    _, md = unpack.unpack(verify=False)
    return script.load_mesarc(md)


def test_every_string_roundtrips(mesarc):
    font, msgs = mesarc
    enc = script.Encoder(font); n = 0
    for name, (cb, ob) in msgs.items():
        offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
        md = script.MdFile(decompress(cb), offs)
        cmds = list(md.cmds)
        for i, cs in enumerate(md.strings):
            text = script.codes_to_text(cs, md.base, md.cmds, font)
            assert enc.encode(text, md.base, cmds, f'{name}[{i}]') == cs, f'{name}[{i}]'
            n += 1
        assert cmds == md.cmds, f'{name}: encoder added records'
    assert n == 27635


def test_rebuilt_file_parses_back(mesarc):
    font, msgs = mesarc
    for name in ['ev0201mes', 'btlmes', 'itemdmes', 'staffmes']:
        cb, ob = msgs[name]
        offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
        md = script.MdFile(decompress(cb), offs)
        raw, new_offs = script.build_md(md.base, list(md.cmds), md.strings)
        again = script.MdFile(raw, new_offs)
        assert again.strings == md.strings and again.cmds == md.cmds


def test_tiled_layout_keeps_offsets(mesarc):
    """Changed strings (short, and longer than their slot) decode at the original offsets."""
    font, msgs = mesarc
    n_files = 0
    for name in ['wsy01mes', 'wsy02mes', 'wmn01mes', 'ev0201mes', 'etcmes', 'wdj01_04mes']:
        cb, ob = msgs[name]
        offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
        raw = decompress(cb); md = script.MdFile(raw, offs)
        new = {}
        for k in range(0, len(offs), 2):                     # every other string: alternate short/long
            new[k] = [0x21] * (1 if k % 4 == 0 else 3 * len(md.strings[k]) + 7)
        tiled = script.build_tiled(raw, offs, new)
        again = script.MdFile(tiled, offs)
        for k in range(len(offs)):
            assert again.strings[k] == (new[k] if k in new else md.strings[k]), (name, k)
        n_files += 1
    assert n_files == 6


def test_tiled_reuses_dead_dictionary(mesarc):
    """Every string replaced and longer than its slot (evmnng: 1,004-entry Japanese dictionary): the old
    dictionary area holds rests and the file still decodes at the original offsets."""
    font, msgs = mesarc
    cb, ob = msgs['evmnngmes']
    offs = list(struct.unpack(f'<{len(ob)//4}I', ob))
    raw = decompress(cb); md = script.MdFile(raw, offs)
    new = {k: [0x21 + k % 50] * (3 * len(md.strings[k]) + 11) for k in range(len(offs))}
    with pytest.raises(script.LayoutError):
        script._build_tiled(raw, offs, new, False)
    again = script.MdFile(script.build_tiled(raw, offs, new), offs)
    assert again.strings == [new[k] for k in range(len(offs))]


def test_pack12_odd_even():
    for cs in ([0x123], [0x123, 0x456], [1, 2, 3, 0xFFE, 0xA72]):
        b = script.pack12(cs + [script.END])
        got, nxt = script.codes_at(b, 0)
        assert got == cs and nxt == len(b)
