# WebUI 验收记录 (issue #639) — 2026-11-02

| 检查项 | 状态 | 证据 |
|---|---|---|
| #632 spike：浏览器驱动一轮研究、LLM 全经 pi、零平行配置 | ✅ verified | PR #643：WS/REST 全轮集成（launch→freeze→vitals）；server 永不调模型；pi 配置只读探针 |
| #633 P0/P1：隔离可见、vitals 实时、仅归档可删 | ✅ verified | 双项目零串扰；delete 未归档拒绝 verbatim；归档只读（#644 + closeout） |
| #634 P2：四分路由回执、状态卡唯一动作、纠正同路由 | ✅ verified | slot/claim/hypothesis/parking 四向断言；状态卡跨走查相位（committed→chat 落地=提交后消失的引擎依据）；转写 3×(user+rt) 回放 |
| #635 P3：溯源逐卡、checklist 门、确认冻结 | ✅ verified | 幽灵要素丢弃→诚实缺口；缺口阻止确认 verbatim；确认后编辑=major pivot 拒绝 |
| #636 P4：实况+重放确定、≤3 点击 lineage、问句不是判决 | ✅ verified | 同拍两次请求全等、全场 console=拍数；lineage 三层断言；ghost → no-fake-lineage |
| #637 P5：fork 双端可见、快照不可变、H7 遥测 | ✅ verified | fork_parent/forked 双端断言；继承快照落 chat；fork:/version-continue: 遥测事件 |
| #638 设置：模型切换对新会话生效、key 不回显、审计无名值 | ✅ verified | 写后读校验（auth.json/models-store.json）；read/响应/审计三处掩码断言；变更语义如实披露 |
| 红线走查：状态不裸靠颜色（徽章带文字）；未冻结标注；已提交无修改入口；单源不标已证实 | ✅ verified | 徽章"已决/未决"+文字；草稿行"未冻结·不可跟踪"；快照🔒横幅"不可再修改"；verify_tier 展示不升级 |
| **DOM 级 Playwright 浏览器自动化** | ⏸ deferred（披露） | wire-level e2e 覆盖浏览器发起的全部流量（21/21）；DOM 断言属浏览器基础设施 provision（CI 无浏览器），随 keyed-session/CI 扩展落地。前端本身由 tsc strict + vite build + #632 本地双进程冒烟（页面可达、/api 代理通、真实 ~/.pi/agent 读取）覆盖 |
| 验收记录落盘 | ✅ | 本文件 |

**结论**：WebUI 波次退出标准达成（DOM 级自动化为已披露的基础设施延迟项，非功能缺口）→ milestone #10 关闭。

**失败信号**：走查任一断言红；掩码断言红（key 泄漏）；重放不确定；lineage 伪造路径。
