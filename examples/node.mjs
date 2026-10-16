// Node.js host example. Install auto-effort first; set its backend credentials.
// Read a request from stdin; select effort before your host issues its agent call.
import { spawn } from "node:child_process";

let request = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) request += chunk;

const selector = spawn("auto-effort", ["pick", "--format", "json"], {
  stdio: ["pipe", "pipe", "inherit"],
  shell: false,
});
let output = "";
selector.stdout.setEncoding("utf8");
selector.stdout.on("data", (chunk) => { output += chunk; });
selector.stdin.on("error", () => {}); // The exit event reports a failed selector.
selector.on("error", () => {
  console.error("auto-effort is unavailable; install the CLI before using this example");
  process.exitCode = 1;
});
selector.on("close", (code) => {
  if (code !== 0) {
    process.exitCode = 1;
    return;
  }
  try {
    const decision = JSON.parse(output);
    // Supply this setting to your agent request along with the original request.
    console.log(JSON.stringify({ reasoning: { effort: decision.effort } }));
  } catch {
    console.error("auto-effort returned invalid JSON");
    process.exitCode = 1;
  }
});
selector.stdin.end(request);
