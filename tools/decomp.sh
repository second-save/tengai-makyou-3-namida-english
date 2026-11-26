#!/bin/sh
# usage: tools/decomp.sh OUTFILE func1 func2 ...
cd "$(dirname "$0")/.." && /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless work/ghidra namida -process SLPM_659.52.analysis -noanalysis -readOnly \
  -scriptPath tools/ghidra_scripts -postScript Decomp.java "$@" 2>&1 | grep -E "ERROR|Exception" ; true
