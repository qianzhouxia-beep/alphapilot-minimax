---
project: alphapilot
domain: architecture
title: Shadow 对比自动分析闭环：cron 16:26 自动出生产 vs 候选 Top2 报告
date: 2026-08-15
status: decision
tags: [RD, shadow, 自动分析, cron, 报告]
source_chat: shadow 自动分析闭环
---

# Shadow 对比自动分析闭环

## 结论

在影子并行试运行（`knowledge/inbox/2026-08-15-rd-shadow-parallel.md`）基础上，新增**自动分析闭环**：每个工作日 16:26（K线 16:15 fix + 16:18 sync 完成后），cron 自动跑 `scripts/shadow_top2_report.py`，读 `output/shadow_top2_history.jsonl`，算生产 Top2 vs 候选 Top2 的 T+0收盘→T+1/T+2 累计涨幅对比，写 `output/shadow_top2_report.{json,md}`，**样本≥8 天自动下"候选更优/生产更优/方向不明"结论**。无需用户手动触发。

## 每日自动闭环（已就位）

| 时间 | 任务 | 产出 |
|---|---|---|
| 09:35 | morning_live 选股（含 shadow 旁路） | `shadow_top2_history.jsonl`（生产+候选 Top2） |
| 09:40 | archive_daily_picks（已有） | `daily_picks_archive/*/top2.json` |
| 16:15 | fix_kline（已有） | `kline_all.parquet` 更新 |
| 16:18 | sync_kline_root（已有） | 根目录 kline 同步 |
| 16:25 | accumulate_top2_t1t5（已有） | 生产 Top2 T+1~T+5 报告 |
| **16:26** | **shadow_top2_report（新增）** | **生产 vs 候选 T+1/T+2 对比报告 + 自动结论** |

## 关键点

- `shadow_top2_report.py` 口径与 `accumulate_top2_t1t5.py` 一致（T0收盘买入、T+n累计涨幅），两份报告可比。
- 结论阈值：到期样本（有 T+2）≥8 天才下结论；候选胜率 ≥60% 且平均差 >0 → `CAND_BETTER`，≤40% 且差 <0 → `PROD_BETTER`，否则 `INCONCLUSIVE`。样本不足显示"累积中"。
- 已验证：干跑（mock 2 日）输出正确，逐日对比/明细/汇总/结论全正常；测试后已清理。
- cron 已挂 `26 16 * * 1-5`，备份 `crontab.bak_pre_shadow_20260815_234327`。

## 下一轮工作

- 周一 08-17 起自动累积 shadow 记录；1~2 周后 `output/shadow_top2_report.md` 的结论区会给出"候选是否优于生产"。
- 若 `CAND_BETTER` → 人工对照 `PROMOTION_CHECKLIST.md` 评审 08-15 候选提前晋升；若 `PROD_BETTER` → 候选不晋升，考虑 RD 因子方向调整。
