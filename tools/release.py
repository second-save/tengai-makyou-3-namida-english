#!/usr/bin/env python3
"""Build and package a release: release/Namida_EN_vVERSION.zip (xdelta3 patch + README.txt, decision D24).

usage: .venv/bin/python -X utf8 tools/release.py VERSION [--force] [--skip-gates]

Stops at the first failure. Order: content gates (docs/polish.md all ticked, README.md filled in from the
fan-translation-template, `batches.py check`; cheap, so they run first) -> release build -> pytest -> smoke on a
--debug build (build/en_dbg.iso) -> no debug patch in the release ELF -> rom SHA-1 -> xdelta3 patch -> re-apply
to the original in a temp image, compare SHA-1, delete it -> zip.
--force       overwrite an existing release/Namida_EN_vVERSION.zip
--skip-gates  dry run: skip the content gates, build and verify the patch, but write no zip
"""
import hashlib, importlib.util, os, re, struct, subprocess, sys, zipfile, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
PY = os.path.join(ROOT, '.venv', 'bin', 'python')
XDELTA = '/opt/homebrew/bin/xdelta3'
ROM = os.path.join(ROOT, 'rom', 'namida.iso')
BUILD = os.path.join(ROOT, 'build', 'namida_en.iso')
DBG = os.path.join(ROOT, 'build', 'en_dbg.iso')
BASE_NAME = 'Tengai Makyou III - Namida (Japan).iso'

_g = importlib.util.spec_from_file_location('guard_bash', os.path.join(ROOT, '.claude', 'hooks', 'guard_bash.py'))
guard = importlib.util.module_from_spec(_g); _g.loader.exec_module(guard)


def unticked(polish_text):
    return [l for l in polish_text.splitlines() if re.match(r'\s*- \[ \]', l)]


def readme_problems(text):
    """The template's placeholders (same list as the guard hook) and its 'Translation status' table."""
    left = sorted({m.group(0) for m in guard.PLACEHOLDER.finditer(text)})
    out = [f'template placeholders left: {" ".join(left)}'] if left else []
    if not re.search(r'^#+ *Translation status', text, re.M | re.I):
        out.append("no 'Translation status' section: README.md is not written from the fan-translation-template README")
    return out


def debug_hooks(elf):
    """Debug-patch hooks (tools/debugpatch.py) that no longer hold their original instruction."""
    import debugpatch as d
    orig = {d.HOOK: d.nor(d.A0, d.ZERO, d.A0), d.MOVIE_HOOK: d.lui(d.A2, 1), d.ENC_HOOK: d.addiu(d.SP, d.SP, -0x30)}
    return [hex(va) for va, ins in orig.items() if struct.unpack_from('<I', elf, va - d.BASE)[0] != ins]


def fail(msg): sys.exit(f'RELEASE FAILED: {msg}')


def step(name, cmd):
    print(f'== {name}: {" ".join(cmd)}', flush=True)
    if subprocess.run(cmd, cwd=ROOT).returncode: fail(name)


def sha1_crc(path):
    h, crc = hashlib.sha1(), 0
    with open(path, 'rb') as f:
        while b := f.read(1 << 24): h.update(b); crc = zlib.crc32(b, crc)
    return h.hexdigest(), f'{crc:08x}'


def readme_txt(version, size, sha, crc, out_sha, out_crc, patch_name):
    return f"""Tengai Makyou III: Namida - English fan translation v{version}

Unofficial fan translation. Not affiliated with Hudson, Red Company or Konami.
No disc image is distributed: you need your own dump of the game.

Base image (Redump: {BASE_NAME[:-4]}, PlayStation 2, SLPM-65952)
  Size    {size} bytes
  CRC32   {crc}
  SHA-1   {sha}

Patched image
  CRC32   {out_crc}
  SHA-1   {out_sha}

How to apply
  Check the base image's SHA-1 first: the patch only applies to this exact dump.
  Command line (xdelta3):
    xdelta3 -d -B {size} -s "{BASE_NAME}" {patch_name} "Namida_EN.iso"
  Windows: xdelta UI or Delta Patcher. Choose the patch and the original image, then apply.
  Tested in PCSX2 2.8.
"""


def main(argv):
    if not argv or argv[0].startswith('-') or set(argv[1:]) - {'--force', '--skip-gates'}: sys.exit(__doc__)
    version, force, skip = argv[0], '--force' in argv, '--skip-gates' in argv
    zip_path = os.path.join(ROOT, 'release', f'Namida_EN_v{version}.zip')
    patch = os.path.join(ROOT, 'build', f'Namida_EN_v{version}.xdelta')
    if os.path.exists(zip_path) and not force and not skip: fail(f'{zip_path} exists: pass --force to overwrite')

    if skip:
        print('!' * 72 + '\n!!! --skip-gates: polish/README/batches gates SKIPPED. Dry run: NO zip will be written.\n'
              + '!' * 72, flush=True)
    else:
        left = unticked(open(os.path.join(ROOT, 'docs', 'polish.md'), encoding='utf-8').read())
        if left: fail(f'{len(left)} unticked line(s) in docs/polish.md:\n' + '\n'.join(left))
        if not os.path.exists(os.path.join(ROOT, 'README.md')):
            fail('README.md missing: write it from the skill\'s fan-translation-template README (pipeline.md §Release)')
        bad = readme_problems(open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read())
        if bad: fail('README.md: ' + '; '.join(bad) + ' (pipeline.md §Release)')
        step('batches check', [PY, '-X', 'utf8', 'tools/batches.py', 'check'])

    step('build', [PY, '-X', 'utf8', 'build.py'])
    step('pytest', [PY, '-X', 'utf8', '-m', 'pytest', '-q', 'tests'])
    step('debug build', [PY, '-X', 'utf8', 'build.py', '--debug', '--out', DBG])
    step('smoke', [PY, 'tools/pcsx2.py', 'smoke', DBG, '--out', os.path.join(ROOT, 'work', 'qa', 'smoke')])

    import iso
    with open(BUILD, 'rb') as f:
        fo = iso.Disc(f).files['/SLPM_659.52']; f.seek(fo.lba * iso.SEC); elf = f.read(fo.size)
    if hooks := debug_hooks(elf): fail(f'release ELF carries the debug patch at {", ".join(hooks)}')
    print('== release ELF: no debug patch')

    from check_rom import check
    check()                                        # rom/namida.iso matches rom.sha1 (exits otherwise)
    size = os.path.getsize(ROM)
    # default level: -9 with -B 4.6 GB ran for an hour without writing a byte; the default takes ~25 s (1.4 MB)
    step('xdelta3 encode', [XDELTA, '-e', '-f', '-B', str(size), '-s', ROM, BUILD, patch])
    tmp = os.path.join(ROOT, 'build', 'reapply.tmp.iso')
    try:
        step('xdelta3 re-apply', [XDELTA, '-d', '-f', '-B', str(size), '-s', ROM, patch, tmp])
        got = sha1_crc(tmp)
    finally:
        if os.path.exists(tmp): os.remove(tmp)     # 4.6 GB: never keep it
    want = sha1_crc(BUILD)
    if got != want: fail(f're-applied image {got} != build {want}')
    print(f'== verify OK: patch {os.path.getsize(patch):,} bytes, patched SHA-1 {want[0]} CRC32 {want[1]}')

    if skip:
        print(f'!!! --skip-gates: dry run, no zip written (patch left at {patch})'); return
    sha, crc = sha1_crc(ROM)
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as z:
        z.write(patch, os.path.basename(patch))
        z.writestr('README.txt', readme_txt(version, size, sha, crc, *want, os.path.basename(patch)))
    print(f'== {zip_path}')


if __name__ == '__main__':
    main(sys.argv[1:])
