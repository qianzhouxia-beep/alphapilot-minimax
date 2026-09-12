---
project: alphapilot
domain: data
title: 轨道B QMT模拟盘 09-09 无买入交叉验证 + 服务器 live pool 数据乱值 bug
date: 2026-09-09
status: conclusion
tags: [track_b, qmt-sim, no-buy, data-bug, fullpool-live, r5]
---

# 轨道B QMT 模拟盘 09-09：全天无买点（代码重放验证）

> 用户观察「轨道 B QMT 模拟盘今天应该也没有买入」。用服务器数据 + 部署版策略代码离线重放交叉验证 → **结论：0 买入是符合策略设计的**，但同时暴露一个**服务器 live pool 间歇性数据乱值 bug**（需 WB 修）。

## 一、服务器 09:36 live pool（Track B 买入候选源）

`20260909.fullpool_live.json`：n=19，**money_flow_pass=0**。

- **rank 1-12（12 只）data_error**：`abr=5,884,096 异常 | chg=489 异常`（chg 甚至有 1001/-254）→ drop_reason=`|data_garbage` → 服务器 export_qmt_scores.py 合理性兜底（abr∈[0,1]、chg∈[-30,30]）**强制 money_flow_pass=False**。即 Top 候选（中原内配 r1、美利云 r2、云南锗业 r3、东山精密 r4、宝新能源 r5、大港股份 r6 等）不是"资金弱"，是**源数据被喂了乱值**。
- rank 13-19（7 只）无 data_error 但 money_flow_pass 仍 False → 真实资金闸/换手不足等原因。

**同 bug 历史**：09-02 全池 31 只全 data_garbage（money_pass=0）；09-08 3/24；09-09 12/19。**间歇性、静默**，发作日整条 Track B 买入侧被清空。

## 二、QMT 侧重放（部署版 `TrackB_track_b_qmt_auction_sim_v2.12.py`=v2.12 逻辑，离线 import）

- 买入判定：09:36 起 live pool → LIM10 只在 money_flow_pass 内取 limit_cnt_10d 前 2 → money_pass=0 时**主档空**；代码 else 分支会落 fallback（rank≤10 早盘 / ≤15 10:00 后、非 fund_hard_fail）。
- 用服务器 `data/kline5m/*.parquet`（09-09 全天 5m bars，bar 时间戳同 QMT 规约）+ 策略同款 P2（爬升+VWAP+量比1.3+无追高+日高0.85）、R5（gap±1.5%/竞价量<1.5×/<11:00）、滑点2%、买入窗（早≤11:30/午 13:00-14:00）逐 bar 重放 → **0 成交**。
- 各候选最早 P2 触发（忽略一切闸门）：中原内配 14:45、美利云 15:00、东山 14:20、光洋 14:10、海康 11:00 —— 全在买入窗（14:00 硬收）之外或 R5-time（≥11:00）弃；早盘无候选触发。唯一"干净"的 002708 光洋（gap0/call0.82/rank14）P2 也要 14:10 才满足。盈新发展 10:25 / 粤海饲料 10:30 虽早盘触发但 rank>15 永不买 + r5_call 5.7×/2.0× 弃。
- 局限：5m 边界重放，盘中 intra-bar 首次触发可能被漏；账户假设空仓（实盘若已满 4 仓需 rotation 前置）；001232 无服务器 k5m。

## 三、结论与建议

1. **Track B QMT 模拟盘 09-09 无买入 = 预期行为**（弱市 + 资金闸 0 通过 + P2/R5/rank/窗口全部拦截），与实盘一致，不是策略没跑。
2. **服务器 live 数据乱值 bug 需修**（WB 域）：查 `morning_live_fund_select`/export 上游 live_abr、live_change_pct 的源缩放（同花顺表头漂移类），加 `n_data_err>0` 告警 + 每日留存 fullpool_live 历史供比对。
3. 待查：Track A 09-09 候选是否也被同一乱值殃及（Track A 走 candidates.json 非 live pool，但上游 money gate 同源需确认）。

## 证据与产物

- 数据：`bt_research/cursor_trackb_0909/`（09-01..09 全 fullpool*.json + 18 只 k5m parquet）
- 重放脚本：`bt_research/cursor_trackb_replay.py`（离线 import 部署 sim 代码，可复用 09-10）
- 服务器侧：`export_qmt_scores.py` ~L1015 数据兜底段；`data/kline5m/` 5m bars

## 更新（2026-09-09 22:10）：bug 已修复并部署

老板拍板 Cursor 修。改动：
1. **`live_fund_flow.py` 源头净化**（服务器，工作副本 `bt_research/cursor_trackb_fix/live_fund_flow.py`）：
   `_fetch_batch` 对 f84（→abr，/100 须∈[0,1]）、f170（→chg，须∈[-30,30]）范围校验，越界/缺失置 `None`；读取端 `_cleanf` 把 DataFrame NaN 还原 None → `morning_live_fund_select._merge_ths_into_items` 的 `is not None` 自动跳过，live 字段不再被乱值覆盖。
2. **`export_qmt_scores.py` 兜底加告警**（`production_strategies/server/` 归档权威副本，md5 与服务器一致）：保留强制 fail（NaN 安全化），命中即落 `output/qmt_scores/{date}.data_alert.json`，杜绝"静默清空 Track B"再次无痕。

验证：AST 双过 + 6 组单元用例（含 09-09/08-19 实测乱值→None）+ 上传 md5 一致 + 服务器 py_compile 通过。备份 `.bak_20260909_221245` 可回滚。

**09-10 盘后验证点**：`[FULLPOOL_LIVE] 数据异常强制 fail: 0 只` 且无 `20260910.data_alert.json`。
