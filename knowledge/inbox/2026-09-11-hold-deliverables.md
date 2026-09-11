---
project: alphapilot
domain: strategy
title: 首板 hold 落地①轻量纸面观察池 + ②每日更大候选池长期固化（read-only）
date: 2026-09-11
status: decision
tags: [首板回调, 观察池, pool_archive, fullpool, icir_all_scores, g1, hold, read-only]
source_chat: 老板 2026-09-11 "按顺序依次执行完"（待办 hold_paper_pool / persist_fullpool）
---

# 首板 hold 落地：观察池 + 候选池固化

老板 2026-09-11 拍板：首板方向**不上"多因子+情绪周期控仓"大工程**，落地两件轻活（本条覆盖 ① 与另一独立项"更大候选池持久化"）。

## ① 首板 setup 轻量纸面观察池（read-only）

**动机**：首板与现有生产池重合率仅 0.61%、池内排序实测 −0.62%/天 ⇒ setup 只能当**扩容票源**，不能当收益增量或过滤器。故只**观察积累证据**，不排序、不加仓、不改生产管线。

**脚本** `fb_shadow_daily.py`（仓库 `bt_research/_fb_shadow_daily.py`），严格复刻 `bt_firstboard_lift.py` 定义：

- `is_lu` = `close == round_half_up(prev_close*(1+thr),0.01)`，thr = 30x/68x→20%、其余 10%
- 首板 = 当日涨停 且 前 20 交易日无涨停收盘
- setup = 首板在最近 1~5 日内 且 **今日不涨停**

**记录**（append-only `output/fb_shadow/fb_shadow.jsonl`，幂等 dedup `date|symbol`）：
`days_since_fb / pullback / fb_date` + forward：`t1_lu`、`t1_ret_open`、`t1_ret_0935`（5m 09:35 bar close 入场）、`abs3_trail`（+3%锁盈/−4%止损，5m D+1..D+3）。

**Bootstrap（30 交易日，2026-07-31→09-10）**：4263 条，日均 142 只

| 指标 | n | 值 |
|---|---:|---|
| T+1 收盘涨停率 | 4161 | **3.39%** |
| 买 T+1 开盘 → D+1 收 | 4161 | **+0.54%**（胜 52.8%） |
| 买 T+1 09:35 → D+1 收 | 4153 | +0.53%（胜 52.9%） |
| abs3_trail 出场 | 3950 | **+0.52%**（胜 **61.3%**） |

按 `days_since_fb` 分层：1~4 日 +0.53%~+0.65%，第 5 日 +0.39%（略衰减）。

**cron**：`17:20`（在 16:20 `build_kline5m` / 16:35 `fix_kline5m_sina` 之后；与 `g1_shadow_daily` 17:10 同批）。

## ② 每日「更大候选池」长期固化

**动机**：G1 扩样到顶的根因 = 历史候选池未持久化，分组结论永远只能验 ~1 个月。

**核查发现**：服务器**已有全量打分宇宙按日落盘** `output/rf_score_archive/{date}/icir_all_scores.json`（**~499 只/日**；`rd_workshop/research_factory/archive_score_snapshot.py` 每日 09:40 拷贝，**脚本内无滚动清理**）。此前研究只用 top10 归档，没用到它。

**新增固化器** `pool_archive_daily.py`（仓库 `bt_research/_pool_archive_daily.py`）→ append-only `output/pool_archive/pool_archive.jsonl`：

- 每行 `{date, symbol, name, score, source}`
- source = `icir_all_scores`(~499) / `morning_picks` / `fullpool` / `fullpool_live`
- 幂等 dedup `date|symbol|source`；不删不改历史

**Bootstrap**：**31 天（07-24→09-11）/ 17,309 行 / 均值 558 只·日**；by source：icir_all_scores 14308、fullpool 1240、morning_picks 1175、fullpool_live 586。重跑 0 新增。

**cron**：`17:25`。

**边界**：**无法追溯 07-24 之前**（历史就是没存）；只能靠持续累积。日后分组/regime 研究改读这一份，不再受"每天一目录 + 只有 top10"限制。

## 关联

- 首板完整结论：`knowledge/inbox/2026-09-10-firstboard-lift.md`
- G1 扩样瓶颈：`bt_research/_post_issue6_trackA_expand_body.md` §四
- 5m 6 个月回补（hold 的另一半）：`knowledge/data_sources/2026-09-11-kline5m-history-sources.md`
- checkpoint：`knowledge/ops/checkpoints.md` 2026-09-11 21:50 / 22:10 行
