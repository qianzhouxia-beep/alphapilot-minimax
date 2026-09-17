---
project: alphapilot
domain: data
title: v1.1 修复首跑验证 + 两个异常裁定（event_calendar「空」是误报 / sector_heat base_day 是基期语义）
date: 2026-09-17
status: conclusion
tags: [overnight-signal, ingest, event-calendar, g2, sector-heat, first-run, false-alarm]
---

# 结论一：v1.1「显式缺行」首跑按设计工作；但根因是**新浪分标的发布滞后**

## 首跑事实（09-17）
ingest 三次（05:30 / 07:00 / 09:20）日志：

```
[05:30] OK nvda ~2026-09-15 / WARN expected us session for cn 2026-09-17 = 2026-09-16,
        but nvda cache last = 2026-09-15 -> row marked stale (no forward-roll)
[07:00] 同上
[09:20] OK nvda ~2026-09-15 / OK qqq ~2026-09-16 / 同上 WARN
```

信号尾条 = `cn=09-17 ← us=09-16, rets=null, g1_flag=stale, stale_reason=expected_us_session_not_ingested`
——**没有复制 09-15 的旧值**，修复达成预期。

## 新发现：新浪**分标的**发布滞后（不是全市场一起延迟）
- 09:20 时 **QQQ 的 09-16 已到**（4871 rows ~09-16），**NVDA 的 09-16 还没到**（5764 rows ~09-15）；
- 15:41 复查：NVDA 09-16 已到（`n=5765`，close `213.90`）。
- 由于 `prev_us_session` 以 **NVDA** 为准（G1 主锚 NVDA），NVDA 缺一天 ⇒ 整行 stale。

## 处置（已完成）
1. **回填**：15:41 重跑 ingest（NVDA 09-16 已发布）→
   `cn=09-17 ← us=09-16, nvda=+0.008154(+0.8154%), qqq=+0.000255(+0.0255%), g1_flag=none, backfilled=true`
   （`backfill_notes.json` 已加 09-17 说明）。
2. **重打标注**：`g1_20260917.json` 的 g1 块由 `stale` 订正为 `none`（us 09-16 / +0.8154% / +0.0255%，
   `n_rebound_bonus=0`）；镜像 09:38 后已刷新。**仅标注，无重排**。
3. **窗口加密**：晨间重试由 `05:30/07:00/09:20` 加密为
   **`05:30 / 06:00 / 07:00 / 08:00 / 08:30 / 09:00 / 09:20`**（全部幂等，落在 09:38 G1 stamp 之前）。

## 未决
- 若某日 09:20 前 NVDA 仍未发布，该日 G1 只能是 `stale`（缺行优于错值），**G1 当日不可用**。
  可选后续（需老板拍板）：① 增加"实时报价/盘前价"补充源；② 放宽为"NVDA 缺失时用 QQQ 仅在 note 标注"
  （**不建议**：G1 阈值本就锚 NVDA，换锚等于改口径）。

---

# 结论二：`event_calendar` **不是空的** —— WB 侧误报

服务器实查（`knowledge/ops/event_calendar.json`，mtime 09-15 20:36，250B）：

```json
[{"date":"2026-09-17","events":[{"name":"Fed FOMC","time_bj":"02:00","weight":"high",
  "note":"决议后首个 A 股交易日=缺口日；G2 shadow：不追缺口方向"}]}]
```

- 全库仅两处 `event_calendar.json`（源 + `_research/` 镜像），**两者内容一致、均非空**；
- 今日 `g1_20260917.json` 的 `g2` = **`is_gap_day=true, hint=do_not_chase_gap`**，events 正确带出 Fed FOMC。
- 结论：**G2 今天正常吃到该事件**。WB 报的「空 `{}`」应是其侧解析/取件问题——注意本文件是
  **list schema**（`[{date, events}]`），不是 dict；用 `cal.get("date")` 之类按 dict 取会得到空。
  已请 WB 用 list 口径复核并给出其读取路径。

---

# 结论三：`sector_heat.base_day=09-15` 是**基期语义**，不是 stale

`scripts/stamp_sector_heat_d1.py` 定义：`ret = close(d1)/close(d2) - 1`，其中
`d1 = prev_trade_day(asof)`、`d2 = prev_trade_day(d1)`。

故 09-17 当日产出：`asof_cn=09-17`、**`ret_day=09-16`（=D-1 ✓）**、**`base_day=09-15`（=D-2，收益基期）**。
`base_day` 是"算 D-1 收益用的前一日"，**不是**"信号日"——D-1 设计成立，无需修。

## 关联
- 前序：`inbox/2026-09-16-overnight-signal-forward-roll-fix.md`
- `knowledge/ops/checkpoints.md` 2026-09-17 15:50 行
- WB 核验：Issue#6（09-17 盘后汇总）
