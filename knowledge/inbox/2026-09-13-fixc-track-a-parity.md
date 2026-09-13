---
project: alphapilot
domain: strategy
title: Fix C 同步到轨道 A（v2.45→v2.46）——A/B 并行对照必须同修，否则账本精度不同、对照失真
date: 2026-09-13
status: decision
tags: [trade-model, qmt, ghost-ledger, passorder, fill-confirmation, track-a, track-b, ab-comparison, fix-c]
---

# Fix C 同步到轨道 A（v2.45→v2.46）

## 背景：老板纠正了框架理解

此前 Cursor 把 Fix C 的范围红线（"仅 Track B 模拟盘"）理解为"轨道 A 不用修"。**老板 2026-09-13 纠正**：

> 两个模拟端账号（98009473 跑轨道 A、62128716 跑轨道 B）是**并行对照实验**，要比出哪条轨道更好，将来**谁好就把谁上实盘**。既然 B 改了、发现漏洞了，**A 也必须把同一个洞堵上**——否则两轨账本精度不同，对照结论不可信。

⇒ 这是 A/B 对照实验的**公平性要求**：修复必须同修、同口径；只有实盘部署继续推迟（等两轨分优劣）。

## 缺陷（两轨同源）

`passorder` 返回 `ret == 0` **只代表"委托已提交"，不代表"已成交"**。改前两条轨道都在 `ret==0` 后**立即按信号价记账**：

- 买入：写 `position_map`（`buy_price = 信号价`）、`_mark_order_locked`、`_log_trade("BUY")`，并 `today_bought += 1` ⇒ 若未成交：**幽灵持仓 + 贸易日志污染 + 当天买入额度被吃掉**。
- 卖出：`position_map.pop` + `_log_trade("SELL")` ⇒ 若未成交：**幽灵平仓**（账上票消失、券商仍持有、止损不再管它）。

`_sync_holdings`（POSITION 对账）能部分自愈买入侧，但盖不住"成交均价错记 / 额度被吃 / 卖出侧幽灵平仓"。工单 §二.2 早已点明 `track_a/TrackA_..._{sim,live}.py` 属"同一 3 点模式"，只是当时按授权只报不改。

## 处置：与 B v2.14 语义逐点对齐

| 项 | 做法 |
|---|---|
| 开关 | `VERIFY_FILL=True` 默认开；`False` = 逐字节回退旧行为（对照/排障用） |
| 下单 | 三处 `passorder` 带唯一 `userOrderId`（`_next_oref`，A 前缀 `a`、B 前缀 `b`）→ 落进 `order_remark` 供关联 |
| 确认 | `_confirm_pending(C)` 每 bar 在 sell/buy 前调用，用 broker `ORDER`/`DEAL` 复核 |
| 字段名 | `_fval()` **双 API 解析器**（经典 `m_*` 或 xttrader snake_case 都读）——把"现场字段名未定论"这个阻塞点在代码层消解 |
| 成交判据 | 用 `traded_volume` / DEAL 求和，**不猜** `order_status` 枚举 |
| 买入未确认 | 保槽 pending；券商根本没这笔单 → `[GHOST]` 回滚（撤仓、清锁、`sent_today.discard`、不记日志、可重试） |
| 卖出未确认 | **不 pop、不减股**，清锁留仓（fail-safe），等确认或下轮重试 |

### A 专属适配（不能照抄 B）

- A 的 `_log_trade` 带 `pos=` 参数 ⇒ 移植版沿用。
- A 有 **v2.41 D3 买入冷却**（`_mark_cooldown`）：改前在 `passorder ret==0` 后**立即 arm**。Fix C 下若卖单没成交却 arm，会**错误禁买**。故新增 `_arm_cooldown_sell()`，改为**只在 `_confirm_one` 确认 SELL 成交（或仓位已消失）后才 arm**。
- A 的 `_rotation_sell` 在 `VERIFY_FILL=True` 下"返回已卖"的语义未改（`ROTATION_ENABLE=False`，两轨一致，不影响对照）。

## 验证

- 新增 `track_a/_test_order_confirm.py`：**26/26 PASS**；**先红已证**（对 v2.45 跑报 `AttributeError: _next_oref`，证明 v2.45 无此逻辑）。
- A 侧既有回归全绿：`_test_max_cand_rank` 40/40、`_ut_peelcap_v244` / `_ut_peelnextbar_v245` / `_ut_tsdown_v242` / `_ut_dayhigh_v243` ALL PASS、`_test_sell_rotation_v215` 11/11、`_test_rotation_v216` 9/9、`_test_vwap_second_hit` 9/9、`_test_hold_days_trading` 102/102。
- B 侧 `_test_order_confirm` 26/26（仅注释改动，无回归）。
- 行尾仍 **CRLF**（4246 CRLF / 0 单独 LF）；ASCII + AST 通过。
- A sim 新 md5 `9d8ba58234176937e770741df9d464c4`。

## 影响面

- **选股端**：零影响（Fix C 全在交易端 sim）。
- **A 模拟盘**：需老板把 `track_a/TrackA_track_a_qmt_full_chain_sim_v2.46.py`（CRLF）复制到 QMT 模拟盘；次日查 `[INIT] track-A qmt-sim v2.46 … verify_fill=True`。
- **A live / A TDX / B**：本次均不动（B 老板已部署 v2.14）。

## 一句话

**A/B 是并行对照 ⇒ 修复必须同修、同口径**；只修 B 一边，对照就是在比"两个账本精度不同的策略"。
