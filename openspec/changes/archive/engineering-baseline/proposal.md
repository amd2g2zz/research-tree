# Proposal: engineering-baseline

## Why

四项工程基线缺口在 2026-08-29 被裁决为必须解决：lint 门只有 pyflakes 子集（无复杂度/bugbear/参数量检查）、`ruff format --check` 全量红 45 文件且 CI 无此门、hermes loader 测试在 Docker daemon 停机时环境性红、`docs/方案设计.md`/`docs/需求理解.md` 历史脚手架混在治理面。这些缺口让后续 4 个 alpha3 issue 无法在新门下开工。

## What Changes

1. ruff lint select 扩展（C90/PLR/PLW/ARG/SIM/B/I）+ 存量显式豁免；45 个 format 违例文件一次收口；CI 加 `ruff format --check` 与扩展规则门。
2. pydantic 进 dev group + `src/research_tree/schemas.py` 试点边界 + ADR-007 记录与 ADR-001 stdlib-only 的边界。
3. hermes loader 测试 Docker daemon 探针化（CLI 在但 daemon 停机 → 显式 skip 带原因）。
4. 历史文档移入 `docs/history/`，脚手架模式补 `.gitignore`。

## Impact

- pyproject.toml（ruff 配置 + dev 依赖）、src/tests/scripts 45 文件格式化、delivery-governance.yml、tests/test_skill_loader_integrity.py、.gitignore、docs 历史件移动、新 schemas.py + ADR-007。
- 零行为变更：格式化与豁免不改语义；skip 探针不改变 CI 行为（runner 有 Docker）。
