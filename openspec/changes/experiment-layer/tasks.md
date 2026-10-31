# experiment-layer — tasks

- [x] 1. register 预注册（先注册后执行；hypothesis/criterion/min_sample/cost_cap/designer 校验）
- [x] 2. execute 设计者不执行（designer === executor → LedgerIntegrityError）
- [x] 3. recordObservation 序贯停止（posterior ≥ 0.95 且 sample ≥ min_sample 即停）
- [x] 4. checkBudget 阶梯硬门（超 cost_cap → experiment-gated）
- [x] 5. Gates + PR
