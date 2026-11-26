"""tools/release.py gate parsing and the debug-patch check."""
import os
from conftest import ROOT
import release, debugpatch


def test_unticked():
    text = '# Polish\nOne line per finding: `- [ ] id - note`.\n- [x] a - done\n- [ ] b - open\n  - [ ] c - nested\n'
    assert release.unticked(text) == ['- [ ] b - open', '  - [ ] c - nested']


def test_readme_problems():
    assert release.readme_problems('# Game\n## Translation status\n| Part | Status |\n') == []
    bad = release.readme_problems('# <Game title>\nSHA-1 <sha1>\n')
    assert 'placeholders left: <Game title> <sha1>' in bad[0] and 'Translation status' in bad[1]


def test_debug_hooks():
    elf = os.path.join(ROOT, 'work', 'orig', 'SLPM_659.52')
    if not os.path.isfile(elf):
        import pytest; pytest.skip('no work/orig/SLPM_659.52')
    d = open(elf, 'rb').read()
    assert release.debug_hooks(d) == []
    assert len(release.debug_hooks(debugpatch.patch(d))) == 3
