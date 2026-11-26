"""Identity build: with translations ignored, the rebuilt MESARC and disc equal the originals."""
import os, sys, hashlib, tempfile
from conftest import need_iso, ROOT
sys.path.insert(0, ROOT)
import build, unpack, iso


def test_identity_disc():
    need_iso()
    od, md = unpack.unpack(verify=False)
    mesarc, changed = build.build_mesarc(od, md, use_en=False)
    assert changed == 0
    assert mesarc == open(os.path.join(od, 'MESARC.AFS'), 'rb').read()
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, 'x.iso')
        iso.patch(unpack.ISO, out, {'/MESSAGE/MESARC.AFS': mesarc})
        with open(out, 'rb') as f:
            assert hashlib.file_digest(f, 'sha1').hexdigest() == 'e2949c4fed3dbff862ff92e0d021daccef181690'
