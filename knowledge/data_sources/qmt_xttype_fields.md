# QMT `xtquant.xttype` 字段名（实测，2026-09-12）

> 状态：**实测确认**（QMT 模拟盘现场跑探针所得）｜ 层：数据/交易端
> 用途：Fix C（`passorder` 成交确认）、以及任何要读 QMT 委托/成交/持仓的代码。
> 证据原文：`bt_research/_probe_qmt_field_names_2026-09-12.txt`；探针：`production_strategies/track_b/_probe_qmt_order_fields.py`

## 一、结论（一句话）

QMT 的 `get_trade_detail_data()` 返回的是 `xtquant.xttype` 对象，字段名是 **snake_case**（`account_id` / `stock_code` / `traded_volume` …），**不是** CTP 风格的 `m_strXxx` / `m_nXxx`。**类上没有 `__slots__` / `__annotations__` / 类级字段**，字段名只存在于 **`__init__` 的必需位置参数**里（用 `inspect.signature` 取）。

> ⚠️ 反面教材：Fix C 设计票（`bt_research/FixC_ghost_ledger_ticket.md` §三）曾按 CTP 习惯写成 `m_strOrderSysID` / `m_nOrderStatus` / `m_nVolumeTotalTraded` / `m_dAveragePrice` —— **全部不存在**。照此写会 `getattr` 静默回退默认值，**幽灵账原样复现**。故"字段必须先实测"。

## 二、字段字典（实测）

### 查询方式
| `kind` 参数 | 返回类型 | 用途 |
|---|---|---|
| `get_trade_detail_data(acct, "STOCK", "ORDER")` | `XtOrder` | 当日**委托** |
| `get_trade_detail_data(acct, "STOCK", "DEAL")` | `XtTrade` | 当日**成交** |
| `get_trade_detail_data(acct, "STOCK", "POSITION")` | `XtPosition` | **持仓** |
| （`passorder` 异步回调） | `XtOrderResponse` | 下单响应 |

### `XtOrder`（委托）— 16 属性
`account_id`, `account_type`, **`stock_code`**, **`order_id`**（委托编号）, **`order_sysid`**（柜台编号）, `order_time`, `order_type`, `order_volume`（委托量）, `price_type`, `price`（委托价）, **`traded_volume`**（已成量）, **`traded_price`**（成交均价）, **`order_status`**（状态码，int）, `status_msg`, `strategy_name`, **`order_remark`**（下单时的 `userOrderId`）

### `XtTrade`（成交）— 13 属性
`account_id`, `account_type`, `stock_code`, `order_type`, **`traded_id`**（成交编号）, `traded_time`, **`traded_price`**（成交价）, **`traded_volume`**（成交量）, **`traded_amount`**（成交额）, `order_id`, `order_sysid`, `strategy_name`, **`order_remark`**

### `XtPosition`（持仓）— 10 属性
`account_id`, `account_type`, `stock_code`, `volume`（持仓量）, **`can_use_volume`**（可用量）, `open_price`（成本价）, `market_value`, `frozen_volume`, `on_road_volume`（在途）, `yesterday_volume`

### `XtOrderResponse`（下单响应）— 7 属性
`account_id`, `account_type`, `order_id`, `strategy_name`, `order_remark`, **`error_msg`**, **`seq`**（下单请求序号）

## 三、Fix C 的关键含义

1. **成交确认的判据应优先用 `traded_volume`**（ORDER 的已成量 / DEAL 的成交量求和），**而不是猜 `order_status` 的枚举值**——探针里新建实例的 `order_status` 默认是 `0`，现场未取得真实枚举，**magic number 不可靠**。
2. **成交均价**：`XtTrade.traded_price`（逐笔）⇒ 需按成交量加权；`XtOrder.traded_price` 是委托上的成交均价，可直接用。
3. **关联键**：`passorder(..., userOrderId, ...)` 的 `userOrderId` 会落在 `order_remark`（`XtOrder` 与 `XtTrade` 都有）⇒ 用**唯一 remark**（如 `b<日期><序号>`）即可把下单与后续 ORDER/DEAL 精确对上。当前 sim 三个 `passorder` 点传的是**空串 `""`** ⇒ 无法关联，Fix C 必须改成唯一串。
4. **`account_type = 2`** 出现在所有实例上（推测为「股票账户」常量），可作校验位。

## 四、未解决（需交易日实测）

- `order_status` 的**真实枚举值**（未报/已报/部成/已成/已撤/废单……）——周末无委托，探针拿不到。
- `passorder` 后**同一 bar 内**能否立即在 ORDER/DEAL 查到该委托（**时延未知**）⇒ 决定 Fix C 是"同 bar 确认"还是"次 bar 挂起确认"（后者会改买入时点语义）。
- `POSITION` 的 `open_price` 是否即成本价（用于对账）、`on_road_volume` 语义。

## 关联

- Fix C 设计票：`bt_research/FixC_ghost_ledger_ticket.md`（其 §五 Q1 已由本卡回答）
- 探针脚本：`production_strategies/track_b/_probe_qmt_order_fields.py`（只读，不 `passorder`）
- Issue #6 现场回报
