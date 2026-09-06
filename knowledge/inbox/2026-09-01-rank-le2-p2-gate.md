---
project: alphapilot
domain: strategy
title: 轨道 A 买卖端只让 candidates rank 1-2 进 P2
date: 2026-09-01
status: decision
tags: [买卖模型, rank门槛, P2, Top2, QMT]
source_chat: rank<=2 落地
---

# 轨道 A 买卖端 rank≤2 进 P2

## 结论（2-3 句）

用户确认落地的是 **09:35 `candidates.json` 的 rank 1 和 2（Top 2）**，不是口语里的「rank≥2」。资格收窄后 **仍然要过 P2** 才买：趋势 / 量比 / 不追高 / ABR / 甜蜜区 / 先到先得都不变。两只都不过 P2 → 当天不买。`MAX_DAILY_BUY` 本来就是 2。

## 证据

- 22 个可结算日 2026-07-27～08-31：rank≤2 T+1 日均 **+1.62% t=2.14**；全 Top10 +0.67%；rank 3 单档 −0.74%。rank≤3 超额不显著，不采用。
- 实盘 08-28 / 08-31 / 09-01 买入均为 rank≥4，因为旧逻辑对 Top10 先到先得。
- 这是 **candidates.json 顺序**，不是网页 09:38 融合 Top10。

## 会不会经常空仓

不会变成「很多天都买不到」。真实生产 Top10 + P2 回测（15 日 2026-07-20～08-07）：

- **0 笔 2/15（13%）**、买 1 只 11/15（73%）、买满 2 只 2/15（13%）
- 日均成交 1.00，对比旧规则先到先得 1.87（旧规则 15 天没有空仓日，靠 rank 3–10 把仓位填满）
- 那 2 个空仓日，旧规则买的正是 rank 3+——正是本闸门要挡住的

合成 83 日空仓 43% **不能当生产预期**（名单不是 09:35 真实 candidates）。实盘这 3 天买的都是 rank 5/7/10：若当天 Top2 始终不过 P2，新规则就是空仓，这是预期行为。

## 影响 / 下一步

- 生产已改：`MAX_CAND_RANK=2` + `ROTATION_ENABLE=False`，QMT live **v2.29-tpl** / sim **v2.29** / TDX **v2.28** / ptrade **v1.6**。轨道 B 未动（B 的 rotation 仍开）。
- **需要用户手动部署** QMT 实盘 + QMT 模拟 + TDX 模拟；重启后 INIT 应为上述新版本，盘中应见 `[RANK] max=2 keep=2/10`，不应再出现 `[ROT]`。
- 次日不应再买到 rank≥3。空仓是合法结果。满 4 只不再踢最弱腾仓。

## 关联

- `production_strategies/CHANGELOG.md` 2026-09-01 rank<=2 条
- `knowledge/strategies/buy_sell_rules.md` / `selection_vs_execution.md`
- inbox `2026-09-01-rank-le3-gate-backtest.md`（否决 ≤3 的回测）
