# webui-settings

## Why

Issue #638 (WebUI wave row 7, 用户裁定 2026-10-31): WebUI 可自选模型/配 API，但 **必须与 pi agent 配置同源**——pi 的 ~/.pi/agent 是唯一事实源，rt 侧零平行配置；key 永不回显、审计只记 provider 名。

## What changes

- `pi-config.ts` 写路径：`writeProviderKey`（原子写 auth.json：tmp+rename；provider 名校验；写后读校验）、`writeDefaultModel`（models-store.json default+models 列表维护；写后读校验）。
- webui-server RPC：`config.setProviderKey` / `config.setDefaultModel`（审计事件 target=settings:auth:<provider> / settings:model:<model>——**不含 key 值**）。
- webui 设置页：当前配置展示（配置目录/默认模型/providers）、模型下拉+自由输入设默认、provider+key（password 输入，保存后不回显）表单、变更语义说明（新开 pi 会话生效）。

## impact_scope

- `webui-server/src/pi-config.ts`, `webui-server/src/server.ts`, `webui-server/test/settings.test.ts`
- `webui/src/App.tsx`, `webui/src/styles.css`
