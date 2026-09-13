---
project: alphapilot
domain: data
title: kline_all 是 T+1 —— 所有"按交易日对齐"的影子/体检脚本必须用 kline_max 而非墙钟日，否则假告警或真停摆
date: 2026-09-13
status: conclusion
tags: [kline, t+1, shadow, health-check, p1-down, rd-dual-run, data-alignment, ops]
---

# `kline_all` 是 T+1：影子/体检的日期口径必须锚 kline_max

## 事实（2026-09-13 实测）

`data/kline_cache/kline_all.parquet` 的最大交易日 = **上一交易日**（D 日盘中/盘后，max = D−1）。
09-11（周五）实测：`kline_max = 2026-09-10`。

⇒ **任何"每日跑、按某个交易日 asof 对齐"的脚本，都不能把墙钟目标日当成可计算日。**

## 一个根因，三种病

| 组件 | 错误写法 | 后果 |
|---|---|---|
| `shadow_p1_down_daily.py` | asof = 最新归档日（=当天），再判 `asof > kline_max → SKIP` | **每日必 SKIP，真停摆**（P1-DOWN 09-10、09-11 连停 3 日） |
| RD 双跑（turnover / weakscore） | 窗口右端 = kline max_date | 输出天然滞后 1 日（**这是对的**，但台账按墙钟日看会以为漏跑） |
| `shadow_daily_health.py` | 要求输出日期 == 墙钟 asof | 对上述三项**每天报假 ALERT**（真假告警混在一起，真停摆被淹没） |

关键：**同一份 T+1 数据，生产者按 kline_max 对齐是对的，消费者按墙钟日校验是错的**——修生产者的"bug"反而会引入前视。

## 正确口径（已落地）

1. **生产者**：asof 取「**kline 已覆盖的最新归档日**」= `max{archive_day : archive_day <= kline_max}`；并支持 catch-up（一次补多日，幂等 marker）。
2. **消费者（体检）**：kline 依赖项与 `_kline_max_date()` 比较，**不与 asof 比较**；另加 `kdep_fresh` 闸——若 kline 连上一交易日都没覆盖，则一律 FAIL（**真停摆仍然会响**，不被口径修正掩盖）。
3. 输出 JSON 带 `kline_max` / `kdep_exp`，便于事后判断"是真停还是口径差"。

## 复用到别处

- 任何新影子若依赖 `kline_all`，预注册的"健康 = 最近输出日"必须写成「= kline_max（T+1 允许滞后 1 交易日）」。
- 换更快的同日 K 线源（`kline5m` / 盘中源）才能做到"= 墙钟日"，属另一个工程决策，不是 bug 修复。

## 证据

- 修复 commit `98e4acd`；Issue #6 `5651164600` 回帖。
- 验证：P1-DOWN 恢复（事件 13→23，marker asof=09-10）；体检 `--prev-trading --dry` → **OK 20/20**（修复前 3 FAIL）。
