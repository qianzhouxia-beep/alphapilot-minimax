# Candidate Model 晋升检查清单

候选 run_id: ____________  
审核人: ____________  日期: ____________

## 硬门槛

- [ ] 产物仅在 `rd_workshop/candidates/<run_id>/`，未自动写入生产 `models/`
- [ ] **二选一过门**（2026-09-13 起）：
  - 可交易 OOS：`oos.gate.verdict` = `PASS`（天数 ≥40 且 fill/hit 达标），**或**
  - 历史 walk-forward：`walkforward.verdict` = `WALKFORWARD_PASS`（beyond_noise + RankIC lo95>0 + wins≥5/6）
- [ ] **禁止**：因 `INSUFFICIENT_OOS` 干等 40 天 —— 应跑 walk-forward / 回填 `--walkforward-report`
- [ ] `WALKFORWARD_FAIL` / `FAIL` = 诚实否决，勿晋升
- [ ] 已阅读与生产基线的 `comparison.delta`
- [ ] `comparison.suggest_better_or_equal` 为 true，或书面说明为何仍考虑上线

## 人工判断

- [ ] 额外 `rd_*` 因子经济含义可解释，无明显前视/泄漏
- [ ] 训练 AUC 提升不是唯一依据；可交易 hit≥3% / fill / maxDD 已对照
- [ ] 若仅 walk-forward PASS：仍需短 canary（5~10 交易日）+ 自动回滚，再谈落地
- [ ] 决定：**批准 Promotion** / **拒绝** / **继续实验**

## 若批准 Promotion（人工执行）

1. 备份当前 `models/v25_*.ubj` 与 `models/v25_meta.json`
2. 复制候选 `v25_opt_ensemble_*.ubj`、`v25_meta.json`、`extra_factors.parquet`（如有）到 `models/`
3. 若有 `v25_base`，按需同步
4. 跑一次生产 OOS：`python3 -u scripts/run_oos_tradable_top2.py`
5. 观察 1–2 个交易日打分/推荐后再改仓位策略

## 天数不足时怎么跑 walk-forward

```bash
# 推荐：新加坡沙箱（上海 3.6GB 会 OOM）
python3 scripts/sg_sandbox.py --sync --run \
  "rd_workshop/walkforward_oos.py --folds 6 --test-days 21 --control retrain \
   --extra-factors rd_workshop/candidates/<run_id>/normalized_factors.parquet \
   --run-id wf_<run_id>"

# 回填进晋升报告
python3 -u rd_workshop/run_promotion_adapter.py \
  --factors rd_workshop/candidates/<run_id>/normalized_factors.parquet \
  --run-id <run_id> --skip-train --skip-normalize \
  --walkforward-report rd_workshop/walkforward_runs/wf_<run_id>/report.json
```

签字: ____________
