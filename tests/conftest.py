import sys, os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ISO = os.path.join(ROOT, 'rom', 'namida.iso')
WORK = os.path.join(ROOT, 'work')


def need_iso():
    if not os.path.isfile(ISO):
        pytest.skip('no rom/namida.iso')
