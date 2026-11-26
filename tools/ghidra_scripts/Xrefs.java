// List functions referencing given addresses or strings.  args: outfile target...
// target = 0xADDR, or "str:text" to find defined strings containing text
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*; import java.util.*;
public class Xrefs extends GhidraScript {
  void refs(PrintWriter w, Address a) {
    for (Reference r : getReferencesTo(a)) {
      Function f = getFunctionContaining(r.getFromAddress());
      w.println("  " + r.getFromAddress() + " " + r.getReferenceType() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
    }
  }
  public void run() throws Exception {
    String[] a = getScriptArgs();
    try (PrintWriter w = new PrintWriter(new FileWriter(a[0]))) {
      for (int i = 1; i < a.length; i++) {
        if (a[i].startsWith("str:")) {
          String s = a[i].substring(4);
          for (Data d : currentProgram.getListing().getDefinedData(true)) {
            Object v = d.getValue();
            if (v instanceof String && ((String) v).contains(s)) { w.println(d.getAddress() + " \"" + v + "\""); refs(w, d.getAddress()); }
          }
        } else { w.println(a[i]); refs(w, toAddr(Long.decode(a[i]))); }
      }
    }
  }
}
