---
project: alphapilot
domain: data
title: lhb_stale 复发定案——「空响应=确认无数据」毒化 fetched_ok，改为 K 线日历判定 + 自愈
date: 2026-09-17
status: conclusion
tags: [lhb, 龙虎榜, data-gate, preflight, akshare, trading-calendar, self-heal]
---

# 结论：lhb_stale 复发根因 = 未发布时的空响应被永久标记为已完成

## 现象
`2026-09-17 00:30:23` 预检 FAIL：`[lhb_stale] lhb最新日 2026-09-14 落后 K线 2026-09-16 2天`。
09-15 刚修过一次（仅周五晚拉 + 04:45 过早），本次是**复发**，且缺口在两天内从 0 累积到 2。

## 根因（两层）
1. **22:35 拉取时 09-15/09-16 尚未发布**（或 akshare 瞬时 `NoneType`）→ 返回空。
2. **空响应被当成"确认无数据"永久写入 `meta.fetched_ok`** → 之后所有 run（含 00:30/01:30/02:30
   预检的 `repair=lhb`）全部 `continue` 跳过 → 缺口逐日累积到 `lag>=2` 触发 fail。
   - 更隐蔽的是：00:30 预检还会把**"今天"也预标**（09-17 在 00:30 尚未发布 → 记入 fetched_ok），
     于是当晚 22:35 又跳过 09-17 ⇒ **必然隔日复发**。
   - 判据复核（2026-09-17 00:35 实拉）：akshare `stock_lhb_detail_em` 对 09-14/15/16 分别返回
     84/73/73 行 —— **接口没坏、数据存在**，纯粹是"跳过"造成的。

## 修复（`scripts/pull_lhb_history.py` v1.2，已部署）
1. **交易日历判定**：以 K 线缓存 `data/kline_cache/kline_all.parquet` 为真实交易日历
   （`load_kline_calendar`）。空响应仅在「**不在日历内且早于 K 线最新日**」（=周末/节假日）时才确认；
   **在日历内的交易日 + 晚于 K 线最新日的日期（含"今天"）一律不确认**，留待下次重试。
   - 无 K 线日历时退化为「周末 或 早于 7 天」才算确认。
   - 交易日连续空响应达 `MAX_EMPTY_ATTEMPTS=3` 且已过 2 天 → 才放弃（避免真正无数据日无限重试）。
2. **自愈（self-heal）**：每次运行把「近期不在 LHB 数据里、且无法确认为非交易日、却已在
   `fetched_ok`」的日期**强制剔除重拉**——修复历史毒化并阻止再次累积。
3. meta/health 增记 `healed / retry_days / empty_attempts / kline_max`，便于闸门与人工审计。

## 验证（服务器实测）
- 修复版实跑：`self-heal: re-fetching 3 poisoned empty date(s): ['2026-09-17','2026-09-16','2026-09-15']`
  → `ok 2026-09-16 rows=73` / `ok 2026-09-15 rows=73`；`09-17` 仍空 → 正确判 `[trading day, attempt 1 -> will retry]`，
  **不再写入 fetched_ok**（今晚 22:35/23:30 会再拉）。
- `lhb_history.json` max 由 `09-14` → **`09-16`**（= kline max）。
- 预检全绿：`ready=True fail=0 warn=0`，`lhb_stale [ok] lhb=2026-09-16 kline=2026-09-16`。
- 单测 `bt_research/_ut_lhb_pull_v12.py` **13/13**（含"交易日不确认 / 今天不确认 / 周末确认 / 无日历退化"）。

## 调度加固（主跑+兜底，本仓惯例）
- 新增 **23:30 Mon-Fri** `pull_lhb_late`（`--days 30 --retries 3`），落在 22:35 主跑与 00:30 预检之间，
  覆盖"22:35 尚未发布"的窗口，确保次日凌晨 LHB 与 K 线同日。
- 预检 lag 判据（`>=2` fail）**未改**；本次靠"不再毒化 + 自愈 + 23:30 兜底"保证不再累积。

## 红线 / 未决
- 未新增数据源；接口（akshare/东财）本身正常。
- 若某交易日确无 LHB 数据，将在 3 次尝试且过 2 天后放弃并留痕（`empty_attempts`）。
- `output/data_readiness_wecom.state.json` 记录的 09-17 告警去重态，会在 04:50 闸门绿色运行时
  由既有 `maybe_wecom_clear_state` 自动清除（未手工删除）。

## 部署件 md5（服务器 /home/ubuntu/alphapilot）
- `scripts/pull_lhb_history.py` `c93d8f6e9ed61129c9fa96b3a4f20875`（备份 `.bak_20260917_0035`）

## 关联
- 前次修复：`bt_research/_reply_lhb_stale_fix_2026-09-15.md` · checkpoints 2026-09-15 01:25
- `knowledge/ops/checkpoints.md` 2026-09-17 00:40 行
