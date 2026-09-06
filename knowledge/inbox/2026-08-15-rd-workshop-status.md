---
project: alphapilot
domain: strategy
title: RD 工作坊现状盘点：Track A 已挖 4 期候选、0 晋升，生产仍 106 维
date: 2026-08-15
status: observation
tags: [RD, rd_workshop, TrackA, 晋升, 候选, 因子挖掘]
source_chat: RD 现状总结
---

# RD 工作坊现状盘点（2026-08-15）

## 结论

RD（Model R&D Workshop）目前只有 **Track A（Current Model Uplift，现有 VM2.5 特征空间增量挖因子）** 在运转，已产出 **4 期候选**（07-25 / 08-03 / 08-08 / 08-15），每期挖 10 个 `rd_a_*` 增量因子并重训 V25_opt 候选模型。**0 期进入生产**：生产仍是 106 维 V25（trained_at=2026-08-14，`extra_factor_columns=[]`）。Track B（RD-Agent 自研）仅跑过 doctor 检查，未产因子。

## 关键事实

### Track A 候选迭代（每期 10 因子，top_k=10, min_abs_ic=0.01, sample=200/300）

| 候选 run_id | 训练日期 | 当期新增/变化因子 | 候选 V25_opt AUC | 说明 |
|---|---|---|---|---|
| `track_a_current_model_20260725_020108` | 07-25 | 首期 10 因子（ret_range_ma20__ma3、ret_range__ma3、turnover_x_atr_pct、atr_pct__z20、ret_range_ma20__z20、ret_range_ma20__diff3、profit_margin__ma5、ret_20d__z20、macd_hist__ma5、atr_pct__diff3） | 0.7154 | OOS=INSUFFICIENT（训练后无交易日） |
| `track_a_current_model_20260803_232009` | 08-03 | 换入 `rd_a_rd_auction_open_atr_ratio__ma5`（去 atr_pct__diff3） | 0.7107（retrain 后） | 初训 rc=-9（OOM），08-04 重训成功；08-04 曾做过一次 116 维 promotion 试验→**未部署**（`backup_v25_20260804_pre116`） |
| `track_a_current_model_20260808_020117` | 08-08 | 换入 `rd_a_vol_ma_ratio__z20`、`rd_a_atr_pct__ma3`、`rd_a_turnover_ma_20__ma3`、`rd_a_macd_signal__ma5` | 0.7221 | OOS 08-10~08-13 因 volume bug 空池→修复后重跑 6 信号/hit3=50% |
| `track_a_current_model_20260815_020121` | 08-15（今天） | 换入 `rd_a_rsi_14__z20` | 0.7231 | REF 修复后 74 信号/38 天/total 198.1%；OOS 下周一开跑 |

> 候选模型维度 = 106 生产维 + 10 extra（111 维）。116 维是 08-04 试验口径，**不是生产口径**。

### 为什么没进生产

1. 所有候选 `promotion_report.json` verdict 均 `INSUFFICIENT_OOS` / `suggest_promotion_discussion=False`。
2. 晋升硬门槛 `PROMOTION_CHECKLIST.md`：需 `oos.gate.verdict=PASS`（真实 OOS 40 天门槛）+ 人工审核签字。目前 **0 期过审**。
3. `monitor_rd.py` 每日重试 OOS，`AUTO_PROMOTION=FORBIDDEN`。
4. **volume 单位 bug（07-07~08-14）** 让 08-03/08-08 OOS 全空池，RD 空转一个月；已修复并重跑（见 `2026-08-15-rd-oos-pool0-volume-unit-bug.md`）。

## 生产模型状态（不受 RD 影响）

- `models/v25_meta.json`：trained_at=2026-08-14 21:46，`extra_factor_columns=[]`，`workshop_candidate=true`（08-14 有一次重训，但**不带 RD 因子**）。
- 生产打分 `vm25_scorer.py` 有加载 extra_factors 的能力（`models/extra_factors.parquet` 存在且每日更新，12 列含 rd_a_*），但生产 meta 未声明 extra_factor_columns → **实际不 merge，等于没启用**。

## 下一步

- 08-15 候选 OOS 下周一起累积（trained_at=08-15），40 天门槛预计 10 月中下旬才有 PASS 可能。
- 若想加速，可考虑人工审核把某一期候选（如 08-15 AUC 最高）提前对照 PROMOTION_CHECKLIST 评审。
