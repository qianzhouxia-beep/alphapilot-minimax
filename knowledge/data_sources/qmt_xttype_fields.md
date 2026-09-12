# QMT 委托/成交/持仓对象字段名（⚠️ 尚未定论，2026-09-12）

> 状态：**未定论 — 两套 API 混淆，禁止据此落码**
> 触发：Fix C（`passorder` 成交确认）需要真实字段名；2026-09-12 现场跑探针，但**dump 到的可能是错误的对象类型**。
> 证据原文：`bt_research/_probe_qmt_field_names_2026-09-12.txt`；探针：`production_strategies/track_b/_probe_qmt_order_fields.py`

## 一、⚠️ 核心警告：QMT 有两套交易 API，字段命名不同

| API | 取数方式 | 返回类型 | 字段命名 | 本项目生产是否在用 |
|---|---|---|---|---|
| **经典策略 API** | `get_trade_detail_data(acct, "STOCK", "ORDER"/"DEAL"/"POSITION"/"ACCOUNT")` | 各 QMT 策略内置的 `m_*` 对象 | **`m_strInstrumentID` / `m_nVolume` / `m_dOpenPrice` / `m_nOrderStatus` …** | ✅ **是**（全部 QMT/TDX 策略） |
| xttrader API | `xtquant.xttrader` / `xtquant.xttype` | `XtOrder` / `XtTrade` / `XtPosition` | **snake_case**（`stock_code` / `volume` / `can_use_volume` …） | ❌ 否 |

**2026-09-12 探针 dump 的是第二套（`xtquant.xttype`）的类**，而本项目的 `get_trade_detail_data` 用的是**第一套** ⇒ **探针结论疑似张冠李戴。**

## 二、为什么判断"探针 dump 错了对象"（证据）

1. **生产代码长期用 `m_*` 且可用**：`TrackB_…_sim_v2.13.py` 的 `_sync_holdings` 直接 `obj.m_strInstrumentID` / `obj.m_nVolume` / `obj.m_dOpenPrice`（L1008/1010/1013），且 **CHANGELOG 有记录**「用户每日关闭 QMT 再开盘，重启后 `[SYNC] +` 重建持仓丢失内存状态」⇒ **该路径在生产中真实执行过**。若运行时对象是 `XtPosition`（无 `m_*`），`obj.m_strInstrumentID` 会抛 `AttributeError`、持仓永远同步不上 —— 与事实矛盾。
2. **`_diag_today_orders` 内建 48–57 状态枚举**（`m_nOrderStatus`：48 NotReported … 57 Invalid）——这是**经典 QMT API 的状态码**，与 `xttype` 无关。
3. **探针自身的取证缺口**：`_probe_account` 对两账户查 ORDER/DEAL/POSITION **全部 `n=0`**，即**从未拿到任何真实运行时对象**；唯一被 dump 的是脚本主动 `import xtquant.xttype` 后**凭空构造**的类实例。
4. `[PROBE] bound C.acct=None` ⇒ 策略**未在配置里绑定账户**；QMT 经典 API 要求账户在策略账户列表里注册，否则 `get_trade_detail_data` 返回空 —— 这正是 `n=0` 的合理解释。

> ⇒ **待验证的唯一问题**：`get_trade_detail_data` 运行时返回的对象，其字段到底是 `m_*` 还是 snake_case。**在拿到该对象 `type(obj)` + `dir(obj)` 之前，Fix C 不得落码。**

## 三、已知（较可信）的经典 API 字段名 —— 来自**在用生产代码**

以下取自本仓库**正在运行**的策略（`TrackB_…_sim_v2.13.py` 等），可信度：**中高**（有生产执行痕迹）：

| 用途 | 字段 | 出处 |
|---|---|---|
| POSITION 代码 | `m_strInstrumentID` | `_sync_holdings` L1008 |
| POSITION 交易所 | `m_strExchangeID` | L1009 |
| POSITION 持仓量 | `m_nVolume` | L1010 |
| POSITION 成本价 | `m_dOpenPrice` | L1013 |
| POSITION 可用量 | `m_nCanUseVolume` / `m_nCanUseVol` | L1015-1016 |
| POSITION 建仓日 | `m_strOpenDate` | L1014 |
| POSITION 名称 | `m_strInstrumentName` | L1028 |
| ACCOUNT 可用资金 | `m_dAvailable` | L2720 |
| ACCOUNT 总资产 | `m_dBalance` | L2721 |
| ORDER 代码/量/价/状态/时间 | `m_strInstrumentID` / `m_nVolumeTotalOriginal` / `m_dOrderPrice` / `m_nOrderStatus` / `m_strInsertDate` / `m_strInsertTime` | `_diag_today_orders` L988-994 |

**仍未验证**：ORDER 的成交明细字段（`m_nVolumeTraded`？`m_dTradedPrice`？）、**DEAL 的全部字段**（仓库内**无任何在用代码**读 DEAL）、`ORDER` 与 `DEAL` 的关联键字段名。⇒ 这些必须**实测**。

## 四、下一步（决定性实验）

1. **在 QMT 策略配置里绑定账户**（如 `62128716`）——否则一切查询返回空。
2. 跑**修订版**探针（已改为：打印每个返回对象的 `type(obj)` + **完整 `dir()`** + `__dict__`，并**加查 `ACCOUNT`** 类别以便在无持仓/无委托时也能拿到真实对象）。
3. 拿到 `type(obj)` 即可**一步定性**：是 `xtquant.xttype.XtPosition`（snake_case）还是经典 `m_*` 对象。
4. DEAL 的字段名若要确切，需**交易日**（当天有成交）。

## 五、教训

- **"能 import 的类" ≠ "运行时拿到的类"**：`xtquant.xttype` 可 import 不代表 `get_trade_detail_data` 返回它。探针必须 dump **实际返回值**，而不是 import 一个看起来相关的类。
- 本项目第 5 例「注释/自述不是实现证据」的变体：**"类定义"也不是"运行时对象"的证据**。
- 取证必须走**生产同款调用路径**（`get_trade_detail_data`）并打印 `type()`，不能旁路。

## 关联

- Fix C 设计票：`bt_research/FixC_ghost_ledger_ticket.md`（§五 Q1 **重新打开**）
- 探针：`production_strategies/track_b/_probe_qmt_order_fields.py`
- 旧探针输出（含 `POSITION n=0`、`bound C.acct=None`）：`bt_research/_probe_qmt_field_names_2026-09-12.txt`
- `xtquant.xttype` 类字段（**仅作参考，非运行时对象**）：`stock_code` / `order_id` / `order_sysid` / `order_volume` / `traded_volume` / `traded_price` / `order_status` / `order_remark`（`XtOrder`）；`traded_id` / `traded_price` / `traded_volume` / `traded_amount` / `order_remark`（`XtTrade`）；`volume` / `can_use_volume` / `open_price` / `market_value`（`XtPosition`）
