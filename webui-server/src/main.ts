/** Local dev entry: `pnpm -C webui-server dev` → http://127.0.0.1:8787 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { WebUIServer } from "./server.js";

const workspace = process.env.RT_WORKSPACE ?? mkdtempSync(join(tmpdir(), "rt-webui-"));
const port = Number(process.env.RT_PORT ?? 8787);
const server = new WebUIServer({ workspace, piConfigDir: process.env.RT_PI_CONFIG });
await server.listen(port);
console.log(`[rt-webui] workspace=${workspace} → http://127.0.0.1:${port}`);
