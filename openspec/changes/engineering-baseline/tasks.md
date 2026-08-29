## 1. ruff 门扩展与格式收口

- [ ] 1.1 pyproject `[tool.ruff.lint]` select 加 C90,PLR,PLW,ARG,SIM,B,I；per-file-ignores 承接存量
- [ ] 1.2 `ruff format` 收口 45 存量文件；packages/ 经 build 脚本再生成
- [ ] 1.3 CI delivery-governance.yml 加 `ruff format --check` 与扩展 lint 门
- [ ] 1.4 RED→GREEN：`ruff check .` 与 `ruff format --check .` 全绿

## 2. pydantic 边界

- [ ] 2.1 dev group 加 pydantic；`src/research_tree/schemas.py` 试点（extra="forbid" 对齐白名单语义）
- [ ] 2.2 ADR-007 记录边界与回填排期
- [ ] 2.3 RED→GREEN：schemas 导入与 forbid 语义各一条测试

## 3. Docker 探针与脚手架收口

- [ ] 3.1 hermes loader 测试 daemon 探针（停机 → 显式 skip 带原因）
- [ ] 3.2 `docs/方案设计.md`/`docs/需求理解.md` 移入 docs/history/（tracked 移动）
- [ ] 3.3 `.gitignore` 补脚手架模式；确认 docs/research/ 零残留

## 4. 合入

- [ ] 4.1 全量门过 → chore(engineering-baseline) squash 合入
