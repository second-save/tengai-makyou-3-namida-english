"""Dejima (evmndj, relocated): after the build, every message constant in its event modules decodes to the
English line that sat at that old offset (tools/evembed.py rewrite + pinned stubs)."""
import json, os, struct
from conftest import need_iso, ROOT
import afs, evembed, iso, script, unpack
from cmp import decompress

ISO = os.path.join(ROOT, 'build', 'namida_en.iso')


def test_dejima_offsets_follow_relocation(tmp_path):
    need_iso()
    if not os.path.isfile(ISO): import pytest; pytest.skip('no build/namida_en.iso')
    od, md = unpack.unpack(verify=False)
    font, msgs = script.load_mesarc(md)
    old = list(struct.unpack('<1016I', msgs['evmndjmes'][1]))
    rows = json.load(open(os.path.join(ROOT, 'script', 'evmndjmes.json'), encoding='utf-8'))['strings']
    with open(ISO, 'rb') as f:
        d = iso.Disc(f)
        for p in ('/MESSAGE/MESARC.AFS', '/EVENT/EVENTARC.AFS'):
            e = d.files[p]; f.seek(e.lba * 2048); (tmp_path / p.split('/')[-1]).write_bytes(f.read(e.size))
    mes, ev = afs.Afs(str(tmp_path / 'MESARC.AFS')), afs.Afs(str(tmp_path / 'EVENTARC.AFS'))
    new_offs = list(struct.unpack('<1016I', mes.data(mes.index('evmndjmes.ofs'))))
    built = script.MdFile(decompress(mes.data(mes.index('evmndjmes.cmp'))), new_offs)
    enc = script.Encoder(font)
    want = {k: enc.encode(r['en'], built.base, list(built.cmds)) for k, r in enumerate(rows)}
    by_new = {o: k for k, o in enumerate(new_offs)}
    for mod in ('mndj_p.cmp', 'mndj_r.cmp', 'thiraizumi.cmp'):
        data = decompress(ev.data(ev.index(mod)))
        method, uses = evembed.analyse(data, set(new_offs))
        _, vals = evembed.int_table(data)
        for i, u in uses.items():
            if 'msg' in u:
                k = by_new[vals[i]]
                assert built.strings[k] == want[k], (mod, i, k)
        assert len([1 for u in uses.values() if 'msg' in u]) >= 1000, mod
        if mod != 'thiraizumi.cmp':           # the embedded copy is the English file
            p, n = evembed.embedded(data)
            assert data[p:p + 2] == b'MD' and script.MdFile(data[p:p + len(decompress(mes.data(mes.index('evmndjmes.cmp'))))], new_offs).strings == built.strings
