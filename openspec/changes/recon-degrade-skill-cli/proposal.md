# recon-degrade-skill-cli

## Why

Issue #666（post-#660 完整 e2e 走不通根因）：chat.turn 的回应成功但侦查执行抛 `spawn anysearch ENOENT` **拖垮整条 turn**——墙又回来了。anysearch CLI 是 vendored skill（positional query + markdown 输出），不是 AnysearchProvider 假设的 PATH+JSON 形态。

## What changes

- **降级不崩**：recon provider 失败 → 转写落 kind=recon「前期侦查失败：<原因>（回应不受影响）」+ provider.action 审计（outcome=error）+ turn 结果带 recon_error；**回应仍然落盘**——侦查是增强不是主体。
- **SkillSearchProvider**（webui-server/skill_search.ts）：spawn `node <skill>/scripts/anysearch_cli.js search <query> --max_results 5`（vendored CLI，positional query），解析 markdown 结果块为 SearchResult[]；发现序 RT_ANYSEARCH_CLI→~/.agents/skills/anysearch→null；available() 供回退判断。
- server defaultProvider()：skill CLI 存在→SkillSearchProvider，否则 AnysearchProvider（PATH 形态）。

## impact_scope

- `webui-server/src/skill_search.ts` (new), `webui-server/src/server.ts`
- tests: `webui-server/test/recon_degrade.test.ts` (new)
