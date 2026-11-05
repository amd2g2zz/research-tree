# webui-v3-rewrite

## Why

用户反馈：布局反人类、每轮逼问、响应气泡太宽挤侧栏、流式思维链缺失、顶栏扭曲。从零重写 App.tsx + styles.css——ChatGPT 式布局。

## What changes

- App.tsx 全量重写：侧栏（项目→任务树）+ 居中对话流 + 底部胶囊 + 视图切换按钮（思维导图/调研画布）
- rpc.ts：共享 WebSocket RPC + REST client（单连接、turn-delta 流式钩子）
- styles.css：ChatGPT 式极简白（侧栏/气泡/胶囊/连接线）
- 分解面板/演练按钮/converged 动作卡全部移除——确认阶段由 #661 思维导图页承接

## impact_scope

- `webui/src/App.tsx` (rewrite), `webui/src/rpc.ts` (new), `webui/src/styles.css` (rewrite)
