# webui-real-flow

## Why

Issue #655 (user ruling 2026-11-03): 不要示例要可用的实际 UI——去掉 fixture 脚手架；模型配置默认跟随 pi agent（pi 的 models.json providers 才是真实注册表）；页面响应不再模拟；归档进归档文件夹。

## What changes

- `pi-config.ts` 重写：读 **models.json providers**（pi 真实注册表：provider/{name,baseUrl,api,apiKey,models[]}，key 掩码）；readiness=key∧model；`follows_pi_default`（未覆盖→跟随 pi agent 默认）；写路径 upsert models.json（schema 兼容）+ models-store 仅作默认覆盖标记。
- `real-flow.ts`：extractionPrompt（对话转写→pi 结构化 prompt）、parseExtraction（**quote 逐字回查转写**，溯源律机械映射 msg:seq；映射不上→无溯源→被 parseDecomposition 诚实丢弃）、mechanicalPlan（claims_preview→阶段，无 LLM，12h 不变量）。
- server 新 RPC：`decompose.fromChat`（keyed 未就绪 fail-closed，报错指引设置页，不提供模拟提取）、`research.start`（需已确认分解→机械计划→注册 DAG→走查落 research 相位）、`research.freeze`（**人工裁决门**：四态 verdict+摘要→freeze→v0 落库回 chat）。pi 二进制定位：RT_PI_CMD→PATH→已知 scratch 安装；找不到即 fail-closed。
- 前端：删演练按钮与全部 fixture 注入；分解面板=「从对话提取（pi 会话）」+「无拒绝点」勾选+确认→「启动研究」；research 相位顶栏「冻结提交…」裁决模态（GO/NO-GO/PARK/REFRAMED 四选）；设置页显示 pi providers/models 清单+「跟随 pi agent 默认配置」语义+provider upsert 表单（id/baseUrl/model/key）；侧栏归档项目收进可折叠「归档」文件夹。

## impact_scope

- `webui-server/src/pi-config.ts`, `webui-server/src/server.ts`, `webui-server/src/real-flow.ts` (new)
- tests: `webui-server/test/settings.test.ts` (rewritten), `webui-server/test/keyed_session.test.ts`, `webui-server/test/server.test.ts`, `webui-server/test/closeout.test.ts`, `webui-server/test/real_flow.test.ts` (new)
- `webui/src/App.tsx`, `webui/src/styles.css`
