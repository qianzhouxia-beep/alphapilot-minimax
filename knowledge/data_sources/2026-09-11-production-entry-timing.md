---
project: alphapilot
domain: data
title: 生产入场时点 = 选股日 D 当天 09:36（非 D+1）—— 影响所有"归档日+次日"口径的回测
date: 2026-09-11
status: decision
tags: [生产口径, 入场时点, 回测口径, 前视, 校验, 待审计]
source_chat: 板块 streak stage2 复检（Cursor 发现）→ 待跨项复核
---

# 生产入场时点 = 选股日 D 当天 09:36（**不是 D+1**）

> 发现于 `2026-09-10-sector-flow-streak-wb.md` 的 stage2 生产口径复检。**这是一条跨项的数据口径事实，单独成卡。**

## 事实（服务器实测）

| # | 证据 | 内容 |
|---|---|---|
| 1 | `output/daily_picks_archive/<D>/_meta.json` | `archived_at = D 09:40`（**同日早晨**，非 D+1） |
| 2 | cron | `09:35` scanner + `morning_live_fund_select` 终选 → `09:40` `archive_daily_picks.py` |
| 3 | `<D>/top2.json` | `"role":"trade_top2"`、`"note":"当日自动交易候选"`，**并带 `buy_price`** |
| 4 | **`data/paper_trading.json` `trade_log`** | `2026-08-05 09:36 买入 603893 @184.04`、`09:36 买入 600671 @20.71` —— **两只均在 08-05 归档内** |
| 5 | CHANGELOG | 08-18 `09:36 export_qmt_scores.py` → `09:45:01 买入 300591` |

## 含义

1. **生产的选股日 = 买入日 = 归档文件夹日 D**（09:35 终选 → 09:36 买入 → 09:40 归档）。
2. **D 日收盘后的信息（含 D 日 EOD 板块资金流、D 日收盘价）在生产入场时不可得。**
   - 生产可用的板块资金流上界 = **D−1 收盘**。
   - **把"截止 D"的状态用于 D 日入场 = 前视。**
3. **任何用「归档日 D + 次日 D+1 开盘/收盘」的回测口径，都相当于比生产晚一天入场。**
   - 相对（横截面）结论**不一定翻**；
   - 但**绝对收益水平、时点类/择时类结论须重算**。

## 待审计（TODO）

复核以下既有研究用的是哪种口径，标注或重算：
- 五分类研究（WB `wb_top10_gap_direction_study.md`，含 07-26→08-19 扩样）—— 若用"次日开盘"，需标注；
- G1 low-veto replay（`bt_research/_g1_replay.py`）；
- freshness / exit schemes / dayhigh position sweep / factor zoo 等候选池研究；
- 后续所有"生产口径 replay"**默认入场 = D 09:36**（无 5m 时用 D 开盘代理并注明）。

## 关联

- 发现过程：`2026-09-10-sector-flow-streak-wb.md`（stage2 生产口径复检节）
- 报告：`bt_research/bt_sector_streak_replay.md` §I
- Issue#6：终判回帖（R1 未证实/R2 证伪/R4 支持）
