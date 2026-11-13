/** Local entry: `pnpm -C webui-server dev` → http://127.0.0.1:8787 */

import { homedir } from "node:os";
import { join } from "node:path";

import { WebUIServer } from "./server.js";

// 数据目录（#706 P0-5）：默认落 ~/.research-tree——重启不丢数据；
// 仅显式 RT_EPHEMERAL=1 时用一次性临时目录（演示/测试）
const workspace =
	process.env.RT_WORKSPACE ??
	(process.env.RT_EPHEMERAL === "1"
		? `${import.meta.dirname ?? "."}/.ephemeral-${Date.now()}`
		: join(homedir(), ".research-tree"));
// 商业可用底线（#709）：后台 worker 在跑，任何异步异常都不允许静默杀进程
// ——记录后继续服务（前端离开≠调研结束）
process.on("unhandledRejection", (reason) => {
	console.error(`[rt-webui] unhandledRejection: ${String(reason)}`);
});
process.on("uncaughtException", (error) => {
	console.error(`[rt-webui] uncaughtException: ${String(error)}`);
});
const port = Number(process.env.RT_PORT ?? 8787);
const server = new WebUIServer({
	workspace,
	piConfigDir: process.env.RT_PI_CONFIG,
});
await server.listen(port);
console.log(`[rt-webui] workspace=${workspace} → http://127.0.0.1:${port}`);
