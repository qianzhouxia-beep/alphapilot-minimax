# 开盘选股最终方案（生产）

更新日期：2026-07-26

## 结论摘要

- **唯一下单来源**：09:35 全市场终选 → `morning_live_picks` Top2 → 09:36 **全自动**执行（`REQUIRE_ORDER_APPROVAL=0`）  
- **05:00**：美股后隔夜先验（ICIR / overnight_recommend），**不下单**  
- **09:25:55**：今日集合竞价硬门控 + 快照  
- **隔夜重合**：仅轻确认 `OVERNIGHT_OVERLAP_BOOST≈1.03`（禁止只买交集、禁止默认 ≥1.12）  
- **仓位**：`KELLY_ENABLE=1`，平仓写入 Kelly，16:15 反馈闭环重训  
- **持有**：现有 GapSoft / 剥盈 / −10% / T+2 强平不变  

## 日课时间表

| 时间 | 脚本 | 产出 |
|------|------|------|
| 05:00 | `alphapilot_pipeline_v3.py` | `overnight_recommend.json`、`icir_all_scores.json`、临时 `daily_recommend` |
| 09:25:55 | `pre_market_gate.py` | `call_auction_snapshot.json` + 隔夜池竞价标注 |
| 09:35 | `live_momentum_scanner.py` + `morning_live_fund_select.py` | 重写 `daily_recommend`、`morning_live_picks.json` |
| 09:36 | `paper_trading_signals.py` → `trade_executor.py` | TOP2 全自动模拟成交（无人工确认） |
| 09:40 | `archive_score_snapshot.py` + `archive_daily_picks.py` | 分数快照 + `daily_picks_archive/YYYY-MM-DD/{top2,top10_gated,top10_ungated}.json` |
| 16:15 | `run_feedback_loop.py` | Kelly 重训 + `OVERNIGHT_OVERLAP_BOOST` 微调 → `output/feedback/latest.json` |

## 反馈闭环（为什么进模型）

已落地的闭环层：

1. **仓位层**：平仓 → `kelly_learner.record_trade` → 次日 `apply_kelly`（`KELLY_ENABLE=1`）  
2. **轻确认层**：16:15 按近 40 笔胜率微调 `OVERNIGHT_OVERLAP_BOOST`（区间 [1.00, 1.08]）  
3. **选股归档**：每日 TOP2 / 门控 TOP10 / 无门槛 TOP10 落盘，供复验与换模证据  

**不自动覆盖**生产 **VM2.5**（技术 ID `v25`）权重；换主模型仍走 RD Workshop + 人工审核（避免无证据推模）。命名口径见 [`NAMING.md`](./NAMING.md)。

## 配置

见 `config/opening_scheme.env`。安装 cron：

```bash
python3 scripts/install_opening_scheme_cron.py
```

## 文案口径

对外/对内统一说：

1. 「今日推荐 / 可买」= 开盘后终选，不是 05:00 名单  
2. 集合竞价指 **当日 09:25 后实时开盘价量**，不是模型里日 K 代理因子 alone  
3. 交叉验证 = 轻确认，不是硬过滤  
