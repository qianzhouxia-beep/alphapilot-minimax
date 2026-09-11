---
project: alphapilot
domain: data
title: 5m K 线历史「换源 + 分日限速重开」：各源深度实测，唯一 ≥6 个月免费源=baostock（已解黑名单）
date: 2026-09-11
status: conclusion
tags: [5m, kline5m, baostock, 数据源, 回补, 限速, 首板, g1, 入场时点]
source_chat: 老板 2026-09-11 "按顺序依次执行完"（hold 落地②：5m 补到 ≥6 个月）
---

# 5m K 线历史：源深度实测 + 安全重开

## 结论一句话

**能给 ≥6 个月 A 股 5m 历史的可达免费源，只有 baostock 一条**；其余全部在 1 个月内。
baostock 曾因**并发回补拉黑服务器 IP**，现黑名单**已解除**；已按"**单线程 + 逐只限速 + 日配额 + login 超时**"重开，回补进行中。

## 各源 5m 历史深度实测（2026-09-11）

| 源 | 服务器(上海) | Mac | 历史深度（实测） | 备注 |
|---|---|---|---|---|
| **baostock** | ✅ 可用（黑名单已解） | ❌ login 超时 | **≥6 个月**（2015 起） | 唯一达标；**禁止并发** |
| 新浪 `getKLineData scale=5` | ✅ | — | **1023 根 ≈21 交易日**（08-13→09-11） | 生产 5m 兜底已用；带 amount，volume=股 |
| 东财 `push2his kline klt=5` | ❌ http=000（不通） | ✅ | **~1536 根 ≈32 交易日**（07-30→） | `end` 前移也只回到 07-30，**无更长历史** |
| 腾讯 `mkline m5` | — | — | **~640 根 ≈13 交易日** | 服务器侧 301/受限 |
| TDX（mootdx/pytdx） | ❌ 多服务器返回空 | ❌ | 历史上也仅 ~7 天 | 当日 TDX 服务异常（与 09-10 事故同源） |
| 同花顺官方（Fuyao） | — | — | **无分钟 K**（设计不覆盖） | `knowledge/data_sources/hithink.md` |

> 关键教训：**东财服务器不可达 ≠ 全网络不可达**（Mac 能通，但通也只 1.5 个月）；**"6 个月"别在其他源上浪费时间**。

## 安全重开设计（吸取拉黑事故）

脚本：`backfill_kline5m_safe.py`（服务器 `/home/ubuntu/alphapilot/`，仓库 `bt_research/_backfill_kline5m_safe.py`）

- **单线程**，无 shard/无并发（旧版 4-shard 全市场 → 只成功 2.1% + IP 黑名单）
- **逐只限速** `--rate 1.2s`；**日配额** `--quota`（cron 300/日）
- `login` 带 **SIGALRM 15s 超时**（SG/Mac 会无限 hang，不能裸调）
- **服务不可用即退出**，不重试刷 IP
- 只**新增 `datetime < 现有最早 bar`** 的行，绝不改写；原子写 `os.replace`
- 断点续跑：现有最早 bar 已 ≤ `start+7d` 的票自动跳过
- 避开 16:20 `build_kline5m.py` 写入窗口（16:18–16:28 休眠）

## 上线与进度

- 2026-09-11 深夜启动全量回补（待 4884 只）；抽样 **`000001` 已达 2026-03-02 起 6480 根（6 个月）**。
- cron：`0 3 * * 1-5` → `backfill_kline5m_safe.py --quota 300 --rate 1.5`（深夜低峰、分日续跑）。
- ⚠️ 单只 6 个月抓取约分钟级（baostock 从上海较慢），全量需跨日累积；**黑名单风险仍在，严禁再上并发**。

## 与现有 5m 链路的关系

| 任务 | 脚本 | 时点 |
|---|---|---|
| 当日增量（TDX/mootdx） | `build_kline5m.py` | 16:20 |
| 当日缺口补齐（Sina，21 天内） | `fix_kline5m_sina.py` | 16:35 |
| **历史回补 ≥6 个月（baostock）** | **`backfill_kline5m_safe.py`** | **03:00（分日配额）** |

## 关联

- 事故记录：`knowledge/inbox/2026-09-11-kline5m-backfill-baostock.md`
- 日 K 单源加固与多源兜底：`knowledge/data_sources/2026-09-11-kline-fallback-sources.md`
- 用途（为何要 6 个月）：首板/入场分钟衰减样本外验证 `knowledge/inbox/2026-09-10-firstboard-lift.md` §Ext3；G1 完整 replay 需要长 5m
- 脚本：`bt_research/_backfill_kline5m_safe.py`（服务器 `backfill_kline5m_safe.py`）
