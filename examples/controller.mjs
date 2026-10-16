// A persistent controller connection. Requires an installed auto-effort CLI.
// Use --private for an offline smoke check; otherwise the user's configured judge runs.
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

const config = process.argv.slice(2).find((arg) => arg !== "--private");
const command = process.env.AUTO_EFFORT_COMMAND || "auto-effort";
const args = ["serve", ...(config ? ["--config", config] : [])];
const child = spawn(command, args, { stdio: ["pipe", "pipe", "inherit"], shell: false });
const pending = new Map();
let sequence = 0;

function fail(error) {
  for (const entry of pending.values()) entry.reject(error);
  pending.clear();
}
child.on("error", fail);
child.on("exit", () => fail(new Error("selector process exited")));
child.stdin.on("error", fail);
const lines = createInterface({ input: child.stdout });
lines.on("line", (line) => {
  try {
    const response = JSON.parse(line);
    const entry = pending.get(response.id);
    if (!entry) {
      fail(new Error("unmatched selector response"));
      return;
    }
    pending.delete(response.id);
    if (response.error) entry.reject(new Error(response.error.code));
    else entry.resolve(response.result);
  } catch {
    fail(new Error("invalid selector response"));
  }
});

function select(request) {
  const id = String(++sequence);
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    child.stdin.write(JSON.stringify({ ...request, id }) + "\n");
  });
}

try {
  const privateRequest = process.argv.includes("--private");
  for (const request of ["Implement the documented feature", "Fix a typo"]) {
    const result = await select({ request, private: privateRequest });
    // Merge result.settings or append result.cli_args before the host's agent call.
    console.log(JSON.stringify(result));
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  child.stdin.end();
  lines.close();
}
