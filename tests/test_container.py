"""Container formats: CMP, AFS, disc patcher. Identity and roundtrip, on the real disc."""
import hashlib, os, struct, tempfile
import pytest
from conftest import ISO, need_iso, WORK
import afs, cmp, iso


@pytest.fixture(scope='module')
def disc_files():
    need_iso()
    with open(ISO, 'rb') as f:
        d = iso.Disc(f)
        return d.files, d.part_start


def read_file(path, fo):
    with open(path, 'rb') as f:
        f.seek(fo.lba * iso.SEC); return f.read(fo.size)


def mesarc_bytes(files):
    return read_file(ISO, files['/MESSAGE/MESARC.AFS'])


def test_udf_matches_iso9660(disc_files):
    files, part = disc_files
    with open(ISO, 'rb') as f:
        for p, fo in files.items():
            f.seek(fo.udf_fe); d = f.read(iso.SEC)
            l_ea, l_ad = struct.unpack_from('<II', d, 168)
            alen, pos = struct.unpack_from('<II', d, 176 + l_ea)
            assert pos + part == fo.lba, p
            assert struct.unpack_from('<Q', d, 56)[0] == fo.size, p
            crc_len = struct.unpack_from('<H', d, 10)[0]
            assert struct.unpack_from('<H', d, 8)[0] == iso.crc_ccitt(d[16:16 + crc_len]), p


def test_cmp_roundtrip_all_mesarc(disc_files):
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, 'm.afs'); open(p, 'wb').write(mesarc_bytes(disc_files[0]))
        a = afs.Afs(p)
        for i, name in enumerate(a.names):
            b = a.data(i)
            if b[:3] != b'CMP': continue
            raw = cmp.decompress(b)
            assert cmp.decompress(cmp.compress(raw)) == raw, name


def test_afs_identity(disc_files):
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, 'm.afs'); orig = mesarc_bytes(disc_files[0]); open(p, 'wb').write(orig)
        a = afs.Afs(p); n = len(a.ents)
        assert afs.build([a.data(i) for i in range(n)], [a.meta(i) for i in range(n)]) == orig


def test_disc_patch_identity_and_relocation(disc_files):
    files = disc_files[0]
    orig = mesarc_bytes(files)
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'x.iso')
        iso.patch(ISO, out, {'/MESSAGE/MESARC.AFS': orig})
        with open(ISO, 'rb') as a, open(out, 'rb') as b:
            assert hashlib.file_digest(a, 'sha1').digest() == hashlib.file_digest(b, 'sha1').digest()
        bigger = orig + b'\xAB' * 5000
        log = iso.patch(ISO, out, {'/MESSAGE/MESARC.AFS': bigger})
        assert log['/MESSAGE/MESARC.AFS'][2] is True
        assert os.path.getsize(out) == os.path.getsize(ISO)
        with open(out, 'rb') as f:
            d = iso.Disc(f); fo = d.files['/MESSAGE/MESARC.AFS']; pad = d.files[iso.PAD]
        assert read_file(out, fo) == bigger
        assert pad.lba == fo.lba + -(-len(bigger) // iso.SEC)
        assert pad.lba * iso.SEC + pad.size == files[iso.PAD].lba * iso.SEC + files[iso.PAD].size
