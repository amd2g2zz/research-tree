# default-pi-extensions

## Why

Issue #664（用户裁定 2026-11-03）：5 个 pi 扩展加入默认供应清单（与 pi-subagents 并列）：billion-context、@juicesharp/rpiv-ask-user-question、pi-mcp-adapter、context-mode、pi-web-access。pi.dev 是索引页，官方命令均为 `pi install npm:<name>`；npm -g EACCES 机器回退 ~/.pi/agent/npm 本地前缀 + settings 路径引用（pi-subagents 同模式）。

## What changes

- `pi-extensions.ts`：DEFAULT_PI_EXTENSIONS + ensurePiExtensions（幂等：settings 已引用跳过；缺失安装+追加路径；installer/piCommand 可注入）+ extensionStatuses；不静默装（#588）——设置页显式触发。
- /api/config/pi 增 default_extensions 状态；RPC config.installExtensions（审计按名落库）。
- 设置页「默认 pi 扩展」区：5 项状态点 + 「安装缺失扩展」。

## impact_scope

- `webui-server/src/pi-extensions.ts` (new), `webui-server/src/server.ts`
- tests: `webui-server/test/pi_extensions.test.ts` (new)
- `webui/src/App.tsx`, `webui/src/styles.css`
