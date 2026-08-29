## 1. Tests (RED first)

- [x] 1.1 RED: manifest 校验测试先红（6 测试：库内 manifest 无效——真缺陷：recovery/recursive-discovery 域各缺 1 案例）
- [x] 1.2 GREEN: 修正至 10 案例后 6/6

## 2. Assets

- [x] 2.1 manifest（双臂/同模型/非 holdout 声明）
- [x] 2.2 rubric-v1（4 阶段无综合分 + 盲评协议）
- [x] 2.3 run-pilot（可复现执行 + 降级纪律）
- [x] 2.4 validate.py（stdlib 白名单，importlib 文件加载对齐仓库风格）

## 3. Report

- [x] 3.1 pilot-report-v1：框架 + 两臂 not-run 显式声明 + 零伪造

## 4. Gate

- [ ] 4.1 全门 → PR eval/issue-335 → dev
