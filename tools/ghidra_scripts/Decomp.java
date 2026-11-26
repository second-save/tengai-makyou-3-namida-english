// Decompile functions by name or 0xaddr.  args: outfile name1 name2 ...
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.Function;
import java.io.*;
public class Decomp extends GhidraScript {
  public void run() throws Exception {
    String[] a = getScriptArgs();
    DecompInterface di = new DecompInterface(); di.openProgram(currentProgram);
    try (PrintWriter w = new PrintWriter(new FileWriter(a[0]))) {
      for (int i = 1; i < a.length; i++) {
        Function f = a[i].startsWith("0x") ? getFunctionContaining(toAddr(Long.decode(a[i])))
                   : getGlobalFunctions(a[i]).stream().findFirst().orElse(null);
        if (f == null) { w.println("// not found: " + a[i]); continue; }
        DecompileResults r = di.decompileFunction(f, 120, monitor);
        w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint());
        w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// failed: " + r.getErrorMessage());
      }
    }
  }
}
