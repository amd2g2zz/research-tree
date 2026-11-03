/** Async pi runner (issue #670).

spawnSync froze the entire Node event loop for the full duration of every
pi call (45s+ with a reasoning model and extensions) — the whole WebUI
hung: every HTTP/WS request queued behind one synchronous spawn. runPi
spawns **asynchronously** (promise wrapper), keeps the event loop free,
enforces a hard timeout (kill + typed error — a hung pi must not hang the
server forever), and fails closed with the process's own output in the
message so the existing parse layers keep working.
*/

import { spawn } from "node:child_process";

export class PiRunError extends Error {}

export function runPi(command: string, prompt: string, timeoutMs = 300_000): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const child = spawn(command, ["-p", prompt], { timeout: timeoutMs });
    let out = "";
    let settled = false;
    child.stdout?.on("data", (chunk) => {
      out += String(chunk);
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      reject(new PiRunError(`pi spawn failed: ${String(error)}`));
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      if (code === 0) {
        resolve(out);
      } else {
        reject(new PiRunError(`pi exited with code ${code}: ${out.slice(0, 200)}`));
      }
    });
  });
}
