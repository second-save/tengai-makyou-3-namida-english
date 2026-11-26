// Apply "name 0xaddr" symbols and create functions.  arg0 = symbols file
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.*;
public class ApplySyms extends GhidraScript {
  public void run() throws Exception {
    int n = 0;
    for (String line : Files.readAllLines(Paths.get(getScriptArgs()[0]))) {
      String[] p = line.trim().split("\\s+"); if (p.length < 2) continue;
      Address a = toAddr(Long.decode(p[1]));
      if (getFunctionAt(a) == null) { disassemble(a); createFunction(a, null); }
      var f = getFunctionAt(a);
      if (f != null) { f.setName(p[0], SourceType.USER_DEFINED); n++; }
      else createLabel(a, p[0], true);
    }
    println("applied " + n);
  }
}
