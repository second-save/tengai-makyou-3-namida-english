#!/bin/sh
# Recreate the Ghidra project work/ghidra/namida from rom/namida.iso (about 5 minutes).
# Program SLPM_659.52.analysis = ELF with R5900 lq/sq rewritten to ld/sd so stock MIPS64 decodes stack frames.
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
$PY tools/unpack.py >/dev/null
$PY tools/symbols.py work/orig/SLPM_659.52 work/symbols.txt
$PY - <<'PYEOF'
import struct
d = bytearray(open('work/orig/SLPM_659.52', 'rb').read())
for o in range(0x1000, 0x1000 + 0x5e0000, 4):
    w, = struct.unpack_from('<I', d, o); op = w >> 26
    if op == 0x1E: struct.pack_into('<I', d, o, (w & 0x03FFFFFF) | (0x37 << 26))
    elif op == 0x1F: struct.pack_into('<I', d, o, (w & 0x03FFFFFF) | (0x3F << 26))
open('work/SLPM_659.52.analysis', 'wb').write(d)
PYEOF
mkdir -p work/ghidra
/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless work/ghidra namida -import work/SLPM_659.52.analysis -overwrite \
  -processor MIPS:LE:64:64-32addr -cspec default -max-cpu 8 -scriptPath tools/ghidra_scripts \
  -preScript PreOpts.java -postScript ApplySyms.java "$PWD/work/symbols.txt" -postScript FixNoReturn.java \
  > work/ghidra/import.log 2>&1
grep -E "applied|Import succ" work/ghidra/import.log
