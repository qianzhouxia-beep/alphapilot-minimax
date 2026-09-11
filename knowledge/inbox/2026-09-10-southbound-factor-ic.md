---
project: alphapilot
domain: strategy
title: 南向持股因子全池分层 IC（正式版，股数口径）— 增持是反向信号
date: 2026-09-10
status: conclusion
tags: [hk, southbound, IC, factor, 港股通, 反向]
---

# 南向持股因子全池 IC — 正式版（2026-09-10 Cursor，新加坡数据）

## 背景
WB 试点（Top100、市值口径）→ 无 alpha；但其市值口径混入价格污染。Cursor 用**全池（截面日 610~621 只）** + **股数/占比口径**重做，并加 size 分层与长窗。

## 数据与方法
- 新加坡服务器落地（HK_BASE=/home/ubuntu/alphapilot/hk/）：`hk_ggt_pool_20260908.json`（608 池）+ `hk_kline_200d.json`（608×200 交易日 K）+ `hk_mutual_hold_hist.json`（**65 个持股截面日** 2026-06-08→09-08，每天 610~621 只，002 轨）
- 东财 `RPT_MUTUAL_STOCK_HOLDRANKS` 经新加坡拉取：**filter 必须只 URL-编码引号**（括号/等号原样），否则 SG WAF 400——上海无此限制（编码差异坑，已修进 `_hk_south_prep.py`）
- 因子（全股数/占比口径，避免市值=股数×价污染）：
  - `ratio_chg5/20` = HOLD_SHARES_RATIO 变化(pp)；`shares_g5/20` = HOLD_SHARES 相对增速
  - `ratio_lvl` = 持股占比水平
- 收益：D+1 开盘买 → D+{5,21} 收盘卖；披露 T+1 滞后已内置（t 日截面当晚可用）

## 结果（横截面 Spearman rank IC，逐日序列聚合）

| 因子 | FWD5 meanIC | t | FWD21 meanIC | t |
|---|---|---|---|---|
| ratio_chg5 | -0.034 | -3.25 | -0.033 | -2.07 |
| shares_g5 | **-0.047** | **-5.02** | -0.049 | -3.14 |
| shares_g20 | -0.040 | -2.32 | -0.013 | -0.75 |
| ratio_lvl | -0.003 | -0.26 | -0.025 | -2.15 |

**分层 FWD5**（shares_g5）：Q1(减持)=-0.25% … Q5(增持)=**-1.21%** → Q5−Q1 = **-0.96%**
**分层 FWD21**（ratio_chg5）：Q2/Q3 中性 = +2.5~2.8%，Q5(增持) = **-0.60%** → Q5−Q1 = **-2.18%**（同窗大盘普遍上涨）
**Size 三分**（shares_g5 FWD5）：small meanIC=-0.063 (t=-5.81)｜mid=-0.037 (t=-2.83)｜large=-0.030 (t=-1.66)
**时间切半**：负 IC 集中 6 月中~7 月底（shares_g5 t=-7.4），**8 月后转平**（t≈-0.9）

## 结论
1. **南向增持是反向/风险信号，不是正向 alpha**：5 日和 21 日窗都显著负，增持最多组持续跑输（21 日仍 -0.60%，同期大盘正）。WB"无 alpha"结论修正为"有稳定反向结构"。
2. **小盘最强**（small t=-5.8 vs large -1.7）——与 WB"中盘信息含量高"方向部分一致（更准确：越小越反转）。
3. **8 月后转平**：5 日窗负效应 8 月起消失；是否为 regime 变化（南向变准）需更长样本，别据此反向开仓。
4. 减持组无显著正超额（港股做空难），反向利用价值有限；**更实际用法 = 选股/风险维度：规避"南向拥挤增持"的追高票**（尤其小盘），可进 Phase-1 打分作为负向/风险项，**不得**当正向信号直接做多。

## 产物
- 新加坡 `/home/ubuntu/alphapilot/hk/`（池/K线/截面 hist，管线的正式数据归属）
- 本地 `bt_research/hk_us_phase0/`：`hk_kline_200d.json`、`hk_mutual_hold_hist.json`、`_hk_south_ic.py`（FWD 环境变量切窗）、`hk_south_ic_result.json`
- 数据管线坑（SG WAF filter 编码 / 002/004 同构 / T+1 滞后）见 `2026-09-10-hk-us-phase0-probe.md`

## 未决
- 更长样本（≥6 个月）确认"8 月转平"是否 regime 变化
- 条件化：市场强弱/南向总量变化下的 IC 差异
- 若能拿港股通**当日净买**（非持股 diff），或比截面差分更灵敏
