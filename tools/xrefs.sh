#!/bin/sh
cd "$(dirname "$0")/.." && /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless work/ghidra namida -process SLPM_659.52.analysis -noanalysis -readOnly \
  -scriptPath tools/ghidra_scripts -postScript Xrefs.java "$@" 2>&1 | grep -E "ERROR|Exception"; true
