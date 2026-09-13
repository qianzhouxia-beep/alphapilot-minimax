---
project: AlphaPilot
domain: strategy
title: 安慰剂全量校准通过——随机因子不能过晋升门
date: 2026-09-13
status: conclusion
tags: [placebo, walkforward, overfitting, promotion-gate, noise-band]
---

# 安慰剂全量校准通过——随机因子不能过晋升门

## 结论

修好「对照臂必须去掉增量因子」后，全量安慰剂（4964 只 / +3 纯随机因子 / 6 折 × 21 日）在新加坡跑完：

**随机因子不能通过门**（`beyond_noise` 全 false；块自举 RankIC lo95 < 0）。harness 对无用因子**不发假阳性** —— 抗过拟合校准通过。

## 运气阈值（晋升门可直接引用）

| 判据 | 安慰剂结果 | 真候选门槛 |
|---|---|---|
| 折间 `beyond_noise` | 全 false | 必须 true |
| 块自举 RankIC lo95 | −0.00193 | 须 **> 0** |
| Top10 超额 95% 上沿 | ≈ +0.028 pp | 明显超过且 lo95 > 0 |
| 折间 wins | 2~3/6 | ≥5/6 才有区分度 |

聚合：ΔAUC −0.00025（wins 2/6）/ ΔRankIC −0.00066（wins 2/6）/ ΔTop10 +0.013（wins 3/6）。

## 作废说明

上一版 `sg_placebo_full_0913`（Δ≡0）因两臂同训含噪声矩阵作废，见 ADR §6.3.1。

## 链接

`knowledge/decisions/2026-09-13-promotion-gate-redesign.md` §6.3.3 · `bt_research/_sg_out/report_placebo_full.json`
