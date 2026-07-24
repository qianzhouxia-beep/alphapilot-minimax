# Candidate Model 晋升检查清单

候选 run_id: ____________  
审核人: ____________  日期: ____________

## 硬门槛

- [ ] 产物仅在 `rd_workshop/candidates/<run_id>/`，未自动写入生产 `models/`
- [ ] `promotion_report.json` 中 `oos.gate.verdict` 为 `PASS`（非 `INSUFFICIENT_OOS` / `FAIL`）
- [ ] 已阅读与生产基线的 `comparison.delta`
- [ ] `comparison.suggest_better_or_equal` 为 true，或书面说明为何仍考虑上线

## 人工判断

- [ ] 额外 `rd_*` 因子经济含义可解释，无明显前视/泄漏
- [ ] 训练 AUC 提升不是唯一依据；可交易 hit≥3% / fill / maxDD 已对照
- [ ] 决定：**批准 Promotion** / **拒绝** / **继续实验**

## 若批准 Promotion（人工执行）

1. 备份当前 `models/v25_*.ubj` 与 `models/v25_meta.json`
2. 复制候选 `v25_opt_ensemble_*.ubj`、`v25_meta.json`、`extra_factors.parquet`（如有）到 `models/`
3. 若有 `v25_base`，按需同步
4. 跑一次生产 OOS：`python3 -u scripts/run_oos_tradable_top2.py`
5. 观察 1–2 个交易日打分/推荐后再改仓位策略

签字: ____________
