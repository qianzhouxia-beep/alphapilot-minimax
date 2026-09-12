## 【Fix C 起单 · 待设计确认】Track B sim `passorder` 无成交回报校验（幽灵账）——只读定位 + 调用方清单（Cursor 09-12 11:2x）

按你 `5634160271` 的授权（Fix C 可实施、**必须独立 ticket/commit**）与"**涉及共享函数先只读定位、列调用方清单**"的要求，先交设计票，**未动一行生产逻辑**。

### 一、缺口（幽灵账的准确边界）
`passorder` 的 `ret == 0` **只代表"委托已提交"**。当前 `ret==0` 后立即当既定事实记账：

| 处 | 行 | ret==0 后立即 | 若非成交的后果 |
|---|---|---|---|
| 买入 | L2950 | 写 `position_map`（`buy_price=信号价 fill`）+ 写锁 + `_log_trade(BUY)` + `today_bought+=1` | **幽灵持仓**（账上有、券商无），且当天白占额度 |
| 卖出·全 | L2580 | 写锁 + `_log_trade(SELL)` + `position_map.pop` | **幽灵平仓**（账上没了、券商仍持有） |
| 卖出·半 | L2619 | 同上 + `shares -= half` | 同上 + 股数错账 |

**已覆盖、不重复造**：`ret != 0`（明确被拒）v2.11 已处理（不写锁/不记日志）；`_sync_holdings` 用券商 POSITION 对账、且能把"已下 BUY 未成交"标 `pending=True` 保槽。**真正的缺口 = 全仓库无一处 `"STOCK","DEAL"` 查询**，`ORDER` 仅存在于 `_diag_today_orders` 的打印里，不参与决策。

### 二、只读定位：调用方与爆炸半径
- `passorder` 三点全在**自包含**的 track_b sim 内（L2580/L2619/L2950），`_do_sell` / `_do_sell_half` / `_check_buy` 均本文件私有，**无跨文件共享函数**（各 QMT 文件按项目惯例各自独立）⇒ sim 内改，**不触 live / track_a / TDX**，符合红线。
- 同一 3 点模式存在于 live / tdx / v2.6 / track_a 各文件（**本次只报不改**）；sim 验证有效后是否同步 live，需你**单独拍板**。

### 三、建议设计（最小 fail-safe）
新增 `_order_snapshot(code)`（读 ORDER+DEAL）→ `ret==0` 后：
- `Filled` → 用 **DEAL 实际量/均价** 写账（价不再是信号价）；
- `Pending/PartFilled` → 写 `pending=True`，**不记成交日志**，交 `_sync_holdings` 确认；
- `Canceled/Invalid/不存在` → 打印 `[GHOST] not acknowledged` 并**回滚**（不写 position/锁/额度）。
卖出同理：未确认**不 pop**、不记 SELL。加开关 `VERIFY_FILL=True` 可回退对照。不新增任何交易决策。

### 四、验收（先红后绿）
`_test_order_confirm.py` 五条：①买 ret0 但 Canceled ⇒ 无 position/锁/日志（改前红）；②买 Filled 但均价≠信号价 ⇒ `buy_price==DEAL均价`；③卖 ret0 未成交 ⇒ 不 pop、不记 SELL；④卖 Filled ⇒ 正常回归；⑤`VERIFY_FILL=False` 完全回退。

### 五、⛔ 阻塞落码的一个开放问题（需实测，不能猜）
**QMT sim 的 `ORDER`/`DEAL` 字段名必须实测**——成交量字段是 `m_nVolumeTraded` 还是 `m_nVolumeTotalTraded`？`DEAL` 均价是 `m_dPrice` 还是 `m_dTradedPrice`/`m_dAveragePrice`？**猜错会静默取默认值，等于没修。**

我已备好只读探针 `track_b/_probe_qmt_order_fields.py`（纯 ASCII，只查询不交易）：**请老板在 QMT sim 里、有委托的一天，调一次 `probe(C)`，把 `[PROBE]` 行贴回** —— 拿到真实字段名我立即落码（v2.14 + 单测 + 独立 commit）。

另两个非阻塞问题：`passorder` 后同 bar 内能否立即查到 ORDER（需不需要"次 bar 复核"，会改买点语义）；pending 期间是否占 `MAX_HOLDINGS` 槽（建议沿用现有"保槽"）。

—— Cursor
