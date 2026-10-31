# webui-spike

## Why

Issue #632 (WebUI wave row 1): WebUI skeleton + pi-host 接线 spike。架构基线钉死：React+Vite 前端 + Node 后端**内嵌 rt-core**（引擎=库）；**LLM 判断一律经 pi host**（server 永不调模型；研究走查复用 #579 headless 机械；pi 会话驱动在 #552 派发端口接入，#606 pi-host e2e 已实证；CI 用 #607 先例的 mock 边界）；**配置单一事实源 = pi 配置目录**（只读探针，平行配置不存在）；MCP（#553）留作外部出口，不做本服务内部总线。

## What changes

- `webui-server/`（Node TS，ws + tsx）：REST 读（/api/projects、/api/projects/:id/vitals、/api/config/pi）+ WS RPC（project.create / project.registerTask / chat.ingest 四分路由 / research.launch=#579 全链走查）；引擎事件以 JSON 行流向浏览器（与 headless emit 同纪律）。
- `src/pi-config.ts`：pi 配置只读探针（models-store.json 防御式解析 + auth.json **只出 provider 名，key 值永不外泄**——掩码红线测试钉死）。
- `webui/`（Vite React 最小页）：项目列表/建项目、三体征卡、端到端演练按钮（走 #579 全链：分解→签署→研究→冻结提交）、引擎事件流 console、pi 同源配置展示。
- .gitignore 扩展。

## impact_scope

- `webui-server/src/{server,pi-config,main}.ts` (new)
- `webui-server/{package.json,tsconfig.json}`, `webui-server/test/server.test.ts` (new)
- `webui/{package.json,tsconfig.json,vite.config.ts,index.html,src/*}` (new)
- `.gitignore` (append)
