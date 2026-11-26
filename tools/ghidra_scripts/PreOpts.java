import ghidra.app.script.GhidraScript;
public class PreOpts extends GhidraScript {
  public void run() throws Exception {
    setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false");
  }
}
