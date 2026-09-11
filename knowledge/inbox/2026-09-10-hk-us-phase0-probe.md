---
project: alphapilot
domain: data
title: 港股/美股 Phase-0 数据探测 + 港股通池快照（608 只）
date: 2026-09-10
status: conclusion
tags: [hk, us, gtimg, eastmoney, phase0, southbound]
---

# 港股/美股 Phase-0：gtimg US 实测 + 港股通池 bootstrap + 流动性筛（2026-09-10 01:10）
## 更新 02:00：**数据归属改新加坡**（用户纠偏）— sg 五源全通，见下

## 结论
0. **新加坡服务器（43.156.119.47）= 港美股数据/纸盘正式归属**（2026-09-10 01:30 定）。
   - 五源实测全通：HK 报价 `qt.gtimg.cn/q=hk00700`、HK 日K `hkfqkline`（含回购/分红元数据）、US 报价 `q=usAAPL`、US 日K `usfqkline?param=usAAPL.OQ...`、东财 datacenter-web 南向报表。
   - ⚠️ **SG WAF**：东财 filter 必须**只 URL-编码引号**（括号/等号原样），全量 urlencode 反而 400；上海无此限制。
   - 正式数据落 `/home/ubuntu/alphapilot/hk/`：`hk_ggt_pool_20260908.json`（608）、`hk_kline_200d.json`（608×200d）、`hk_mutual_hold_hist.json`（65 截面日 06-08→09-08，610~621 只/日）。
   - 上海仅留 09-08 参考快照，不再承担港美股长期拉取。
1. **美股 gtimg 报价/日K格式已实测打通**（补上 2026-09-09 矩阵的"待测"格）。
   - 报价：`https://qt.gtimg.cn/q=usAAPL`（**裸码**；`usAAPL.OQ` 反而 none_match）。字段序同 A 股/HK 报价，名称 UTF-8。
   - 日K：`https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param=usAAPL.OQ,day,,,N,qfq`（**必须带交易所后缀 `.OQ`**；裸码只回稀疏 2 行垃圾）。返回 `data.usAAPL.OQ.qfqday` = `[[date, open, close, high, low, volume], ...]`，自带复权。
   - ⚠️ **cloud IP 需要 UA 头**：上海服务器不带 UA 的裸 curl → `v_pv_none_match`；带 `Mozilla/5.0...Chrome` + Referer `https://gu.qq.com/` → 正常返回。Mac 本地带不带都通。→ 抓取脚本必须带 UA，否则误判"被限流"（同今晚 chip 的教训）。
2. **东财 `RPT_MUTUAL_STOCK_HOLDRANKS` 实测**（上海服务器 datacenter-web 通）：
   - 最新 HOLD_DATE 是 **T+1**：09-10 00:50 时最新 = 09-08（09-09 港股通持股表明晨才出）。
   - `MUTUAL_TYPE` 002 与 004 全量**完全同构**（各 608 行、数值一致）→ 东财南向持股已合并口径，**抓一次或抓 002/004 去重都行**，别当成两个独立轨。
   - 字段很全：`HOLD_SHARES / HOLD_MARKET_CAP / HOLD_SHARES_RATIO / ADD_SHARES_AMP / HOLD_MARKETCAP_CHG1/5/10 / CLOSE_PRICE / INDUSTRY / PARTICIPANT_NUM` 等——因子（水平/变化/行业）一张表全齐。
3. **港股通池快照（2026-09-08）**：608 只（头部可信：腾讯/建行/中海油/工行/汇丰，31 行业）。
   - 服务器 `/home/ubuntu/alphapilot/hk_ggt_pool_20260908.json` + 本地 `bt_research/hk_us_phase0/hk_ggt_pool_20260908.json`。
4. **60 日腾讯港股日K全池抓取成功**（上海服务器 128s，608/608，0 失败）：605/608 有 09-09 收盘 bar（3 只停牌停在 08-31）。
   - 产物：服务器 `hk_kline_60d.json` + 本地 `bt_research/hk_us_phase0/hk_kline_60d.json`。
   - 流动性（成交额中位，HKD/日）：≥5M=572、≥10M=538、**≥20M=459**、≥30M=394、≥50M=322。
   - **筛选池 ≥20M → 459 只**：本地 `bt_research/hk_us_phase0/hk_ggt_pool_20260908_liquid20m.json`（含 med_amt；阈值可改，脚本 `_hk_kline_60d_fetch.py` 可复跑）。

## 端点速查（服务器实测，写死备用）
| 用途 | 端点 | 备注 |
|---|---|---|
| US 报价 | `qt.gtimg.cn/q=usAAPL` | 裸码 + UA |
| US 日K | `ifzq.gtimg.cn/appstock/app/usfqkline/get?param=usAAPL.OQ,day,,,N,qfq` | 带后缀 |
| HK 日K | `ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=hk00700,day,,,N,qfq` | WB 已验证 |
| 南向持股日表 | `datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_STOCK_HOLDRANKS&filter=(MUTUAL_TYPE="002")(INTERVAL_TYPE="1")(HOLD_DATE='YYYY-MM-DD')` | 上海通 |

## 未决
- 09-09 港股通持股（T+1）→ 明晨重拉替换快照。
- 美股标的池来源待定（Phase-0 只验证了格式，池子后议；用户优先港股）。
- sg 服务器 gtimg US/HK 复测未做（上海已证可达；sg 留到起盘时验）。
- 459 筛选池/日K缓存的**服务器最终归属**（sg 纸盘 vs 上海中转）待起盘部署时定。

## 证据
`bt_research/_probe_hk_us_phase0.py`（00:47）、`bt_research/_hk_kline_60d_fetch.py`（01:00 上海全池）、`bt_research/_hk_pool_bootstrap.py`（00:49）。
