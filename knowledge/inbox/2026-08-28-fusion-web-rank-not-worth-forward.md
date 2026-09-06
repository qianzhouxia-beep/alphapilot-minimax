---
project: alphapilot
domain: strategy
title: 网页融合排名不宜前移到 QMT candidates 顺序
date: 2026-08-28
status: conclusion
tags: [回测, 选股模型, 融合排名, Top2, Top10]
source_chat: 网页融合历史回测是否值得接入 QMT
---

# 网页融合排名不宜前移到 QMT candidates 顺序

## 结论（2-3 句）

同一套 QMT 候选池里，按网页三路融合重排后再取 Top2，T+1 比现行 `candidates.json` 顺序差 **0.44pp**（13 个可配对日里只赢 4 天）。现行 QMT Top2 日均 T+1 **+1.44%**，已经明显好于同池 Top10 的 +0.18%；网页融合 Top2 同期只有 +0.72%。前移排名只会打乱已经有溢价的队列，**暂不接入**。

## 证据

- 口径：T0 收盘买、T+n 收盘累计 %（与 `accumulate_top2_t1t5.py` 相同）；无 P2、无成本。K 线到 2026-08-28。
- 网页榜：`top10_ungated`（score_top10 融合序），2026-07-20 ~ 08-27，28 个交易日。全样本 Web Top2 T+1 **+0.53%** / 胜率 57%（56 票）；Web Top10 T+1 **+0.41%**（278 票）。
- 对齐 QMT 窗口（08-10 起）：Web Top2 T+1 日均 **+0.72%**；QMT Top2 **+1.44%**（14 日）；Web Top10 **+0.26%** vs QMT Top10 **+0.18%**（几乎打平）。
- 池内重排（真正「前移」会改的东西）：T+1 相对 QMT Top2 边缘 **-0.44pp**，4/13 日；Top2 名单与 QMT 相同仅 4/14 日。08-21 网页 Top2（盛屯矿业/江西铜业）不在 QMT 池，重排也买不到。
- 不是融合 IC 实盘学习环，也不是 RD `feedback_auto_tune`。

## 局限

- 配对日只有 13 个 T+1（08-28 还没有次日；08-24 缺网页归档）。
- 纸面收盘买，不是 QMT 先到先得 + P2 的真实成交。
- 07-20~07-24 的 `score_top10_day` 连续两只相同，早期快照质量一般；结论以 08-10 对齐窗口为准。

## 影响 / 下一步

- **选股模型**：继续 `export_qmt_scores.py` 保序；网页融合只做展示。
- 融合 IC 16:15 学权重可以继续，那是另一条线；权重变好后再单独复验，不默认改序。
- 脚本：`bt_research/bt_fusion_web_rank.py`；数字：`output/bt_fusion_web_rank.json`

## 关联

- `knowledge/ops/checkpoints.md`
- `knowledge/strategies/selection_vs_execution.md`
- `knowledge/decisions/index.md`
