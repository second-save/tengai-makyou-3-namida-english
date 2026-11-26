// Clear the no-return flag on every function and re-disassemble fall-throughs
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.app.cmd.function.*;
public class FixNoReturn extends GhidraScript {
  public void run() throws Exception {
    int n = 0;
    for (Function f : currentProgram.getFunctionManager().getFunctions(true))
      if (f.hasNoReturn()) { println("noreturn: " + f.getName()); f.setNoReturn(false); n++; }
    println("cleared " + n);
  }
}
