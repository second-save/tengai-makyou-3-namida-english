"""Release ELF patches apply to the original ELF, stay inside their known places and decode as intended."""
import os, struct
from conftest import need_iso, WORK
import elfpatch, debugpatch
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64, CS_MODE_LITTLE_ENDIAN

MD = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)


def ins_at(data, va):
    return next(MD.disasm(data[va - elfpatch.BASE:][:4], va))


def load():
    need_iso()
    return open(os.path.join(WORK, 'orig', 'SLPM_659.52'), 'rb').read()


def test_patches_stay_in_place():
    elf = load()
    widths = bytes(range(0x60))
    out = elfpatch.patch(elf, widths)
    P, cv = elfpatch.patch_list()
    allowed = {va - elfpatch.BASE + k for _, va, _, _ in P for k in range(4)}
    allowed |= {va - elfpatch.BASE + k for va, _ in cv for k in range(4)}
    allowed |= set(range(elfpatch.TBL - elfpatch.BASE, elfpatch.TBL - elfpatch.BASE + 0x60))
    allowed |= {va - elfpatch.BASE + k for _, va, _, _, room in elfpatch.DATA for k in range(room)}
    diff = {i for i in range(len(elf)) if elf[i] != out[i]}
    assert diff and diff <= allowed
    cave_lo = elfpatch.CAVE
    assert min(va for va, _ in cv) >= cave_lo and max(va for va, _ in cv) < elfpatch.CAVE_END
    debugpatch.patch(out)     # the test-build patch (cave start, before CAVE) still applies on top


def test_branches_decode():
    out = elfpatch.patch(load())
    i = ins_at(out, 0x41DBF0); assert i.mnemonic in ('b', 'beq') and i.op_str.endswith('0x41dc10')
    _, where = elfpatch.caves()
    for va, name in ((0x41E9C4, 'msg_x'), (0x41C480, 'width'), (0x41DDFC, 'plate')):
        i = ins_at(out, va); assert i.mnemonic == 'j' and int(i.op_str, 16) == where[name]
    # every cave ends with a jump back to the instruction after its hook's skipped code
    words = dict(elfpatch.caves()[0])
    dec = {va: next(MD.disasm(out[va - elfpatch.BASE:][:4], va), None) for va in words}   # data words: None
    backs = sorted(int(i.op_str, 16) for i in dec.values() if i is not None and i.mnemonic == 'j')
    assert backs == sorted([0x41E9D0, 0x41C59C, 0x41E114, 0x41195C, 0x41195C,
                            0x40D648, 0x40D688, 0x410890,           # vertical text: step, flag, turned UVs
                            0x1377E8, 0x137810, 0x136AFC, 0x136B20,  # movie subtitle lookup, both play paths
                            0x40D090, 0x40D650,                     # ASCII step scale, both ws_printf2 paths
                            0x40CBC0, 0x40CB80])                    # map region name: set_size, set_color tails
    for va, name in ((0x40D010, 'asc_adv1'), (0x40D5D0, 'asc_adv2')):
        i = ins_at(out, va); assert i.mnemonic == 'j' and int(i.op_str, 16) == where[name]
    for va, name in ((0x40D680, 'vert_flag'), (0x410888, 'turn_uv')):
        i = ins_at(out, va); assert i.mnemonic == 'j' and int(i.op_str, 16) == where[name]
    i = ins_at(out, 0x40D5C4); assert i.mnemonic == 'bnez' and int(i.op_str.split(', ')[-1], 16) == where['vert_step']
    i = ins_at(out, 0x13B278); assert i.mnemonic == 'jal' and int(i.op_str, 16) == where['opening']
    for va, name in ((0x4118B8, 'len_glyph'), (0x41190C, 'len_ruby'), (0x411984, 'len_ret')):
        i = ins_at(out, va); assert i.mnemonic == 'j' and int(i.op_str, 16) == where[name]
    assert struct.unpack_from('<I', out, 0x41E9B4 - elfpatch.BASE)[0] >> 26 == 0x21   # lh


def test_ceil_div_22():
    for px in range(0, 22 * 111 + 1):
        assert ((px + 21) * 745) >> 14 == -(-px // 22)
