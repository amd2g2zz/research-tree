# setup-boot

## Why

Issue #588 (user ruling 2026-10-30: "需要一个 setup 脚本来安装部署相关包和插件和一些 booting 工作", docs 02 §setup 与 boot v2.3): a pi-native setup/boot entry — install the rt-core workspace, provision provider CLI dependencies, report boot readiness. Idempotent; never silently installs.

## What changes

- `setup/setup.ts`:
  - **runSetup** (idempotent): workspace initialization (`.research-tree/` root + ledger migration run); provider provisioning via the injected provisioner (anysearch / agent-browser CLI checks with pinned expectations); **confirm gate** — global installs and credential writes report before executing (the confirm log lands in the report);
  - **doctor**: boot readiness — per-provider availability (named with install guidance, not generic failures), storage writability, MCP mountability (#553), pi session attachment (#552); `overall` ready/attention-required; machine-readable for headless (#579).
- Provider CLI deps provisioned: anysearch + agent-browser (+ markitdown via #590's manifest pattern), versions pinned at provisioning; **pi-subagents default-installed** (per ruling; catalog version pinned) — readiness checks its presence alongside provider CLIs.

## impact_scope

- `rt-core/src/setup/setup.ts` (new)
- tests: `rt-core/test/setup.test.ts`
