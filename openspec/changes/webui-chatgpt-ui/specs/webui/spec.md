## ADDED Requirements

### Requirement: the chat hub is the primary surface (ChatGPT paradigm)

WebUI SHALL 以 ChatGPT 范式呈现：左侧会话列表（项目→任务）+ 居中对话主流 + 底部输入胶囊贯穿所有阶段；分解/研究/版本 SHALL 以右侧画布面板从对话滑出（chat 永不离开），SHALL NOT 回到仪表盘拼卡。

#### Scenario: open lands on chat
- **WHEN** a task is selected from the sidebar
- **THEN** the main column shows the centered chat stream with the sticky composer pill, and 分解/研究/版本 open as sliding canvas panels

### Requirement: all capabilities preserved under the new form

既有能力 SHALL 全部保留：端到端演练、分解草稿/编辑/checklist 门/确认、研究图谱/确定性重放/lineage 抽屉、版本时间线/继续研究/分叉/只读快照、pi 同源设置写（key 掩码）。产品红线 SHALL 保持：徽章带文字（状态不裸靠颜色）、草稿"未冻结·不可跟踪"标注、已提交版本无修改入口。

#### Scenario: red lines render in the new form
- **WHEN** the UI renders a committed task with an archive attempt and a snapshot view
- **THEN** the delete red line surfaces verbatim, the snapshot shows the 🔒 frozen banner, badges carry text, and the draft row is labeled 未冻结·不可跟踪
