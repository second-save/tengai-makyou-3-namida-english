"""SN Systems DLL modules (dll/**/*.rel, magic SNR1), as read by snDllLoaded (FUN_0042d360).

Header u32s: +4 reloc table, +8 reloc count, +0xc symbol table, +0x10 symbol count, +0x14 entry, +0x18 init,
+0x20/+0x24 pointer table and count, +0x28 alignment. Offsets are file-relative (the loader adds the load address).
Symbol: 12 bytes = name offset, value, u16 section?, u8 type (0 local/defined, 1 import by name, 2-4 other), u8.
Relocation: 12 bytes = offset to patch, u32 (type in the low byte, symbol index in the rest), addend.

    snrel.py FILE.rel     list symbols and the code sites that call each import
"""
import struct, sys


def parse(b):
    assert b[:4] == b'SNR1', b[:4]
    h = struct.unpack_from('<11I', b, 0)
    rel_off, nrel, sym_off, nsym = h[1], h[2], h[3], h[4]
    syms = []
    for i in range(nsym):
        name_off, val, sec, typ, _ = struct.unpack_from('<IIHBB', b, sym_off + 12 * i)
        end = b.index(b'\0', name_off)
        syms.append({'name': b[name_off:end].decode('latin1'), 'value': val, 'type': typ, 'sec': sec})
    rels = []
    for i in range(nrel):
        off, info, add = struct.unpack_from('<III', b, rel_off + 12 * i)
        rels.append({'off': off, 'type': info & 0xff, 'sym': info >> 8, 'addend': add})
    return h, syms, rels


if __name__ == '__main__':
    b = open(sys.argv[1], 'rb').read()
    h, syms, rels = parse(b)
    print('header', [hex(x) for x in h])
    for i, s in enumerate(syms):
        sites = [hex(r['off']) for r in rels if r['sym'] == i]
        print(i, s['type'], hex(s['value']), s['name'], len(sites), ' '.join(sites[:6]))
