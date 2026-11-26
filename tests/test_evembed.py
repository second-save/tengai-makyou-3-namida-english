"""Map modules embed their town's message file (tools/evembed.py): the finder locates it byte-exact."""
import struct
from conftest import need_iso
import afs, evembed, script, unpack
from cmp import decompress


def test_embedded_town_messages():
    need_iso()
    od, md = unpack.unpack(verify=False)
    _, msgs = script.load_mesarc(md)
    ev = afs.Afs(od + '/EVENTARC.AFS')
    for mod, name in [('mttc_p.cmp', 'evmttcmes'), ('mttc_r.cmp', 'evmttcmes'), ('mnng_p.cmp', 'evmnngmes')]:
        data = decompress(ev.data(ev.index(mod)))
        p, n = evembed.embedded(data)
        raw = decompress(msgs[name][0])
        assert data[p:p + len(raw)] == raw and n - len(raw) < 4, mod
