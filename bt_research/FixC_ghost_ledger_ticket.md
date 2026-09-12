# Fix C Ticket — Track B QMT 模拟盘 `passorder` 无委托/成交回报校验（幽灵账）

- 来源：WB-Mac `issuecomment-5634114857` §一(A) / 老板授权 `issuecomment-5634160271`
- 范围：**仅 `production_strategies/track_b/TrackB_track_b_qmt_auction_sim_v2.13.py`**（模拟盘）
- 授权红线：**不碰** `track_b/*_live*.py`、`track_a/*`、服务器选股端
- 状态：**待设计确认后落码**（本 ticket 为"先只读定位 + 调用方清单"交付物）
- 关联已闭环：Fix A（LIM10 fail-open）`fe8f751` + 部署确认 `51818d8`

---

## 一、问题定义（幽灵账）

`passorder` 返回 `ret == 0` **只代表"委托已提交"**，不代表"已成交"。当前代码在 `ret == 0` 后**立即**把结果当既定事实记账：

| 处 | 行 | ret==0 后立即做 | 若非成交（Invalid/Canceled/未触价）的后果 |
|---|---|---|---|
| 买入 | L2950 | 写 `position_map[code]`（`shares`/`buy_price=fill`）、`_mark_order_locked`、`_log_trade("BUY", fill)` | **幽灵持仓**：账上有票、贸易日志记了成交价，券商无票；且当天占用买入额度 |
| 卖出·全 | L2580 | `_mark_order_locked`、`_log_trade("SELL")`、`position_map.pop` | **幽灵平仓**：账上票消失，券商仍持有；止损/peel 不再管它 |
| 卖出·半 | L2619 | 同上 + `pos["shares"] -= half` | 同上，且股数错账 |

**已覆盖的部分（不重复造轮子）**：
- `ret != 0`（明确被拒）已在 v2.11 处理：打印 REJECTED、**不写锁、不记日志**（L2582-2585 / L2621-2624 / L2955-2958）。
- `_sync_holdings`（L994+）每轮用券商 `POSITION` 对账，并能把"已下 BUY 单但未成交"的票标 `pending=True` 保槽（L1066-1069）；买入侧的下轮对账会自我修正。
- `_diag_today_orders`（L973-990）**只用于诊断打印**，不参与决策。

**真正的缺口**：`ret == 0` → **无任何 ORDER 状态 / DEAL 成交校验**，买入价直接取信号价 `fill`（非实际成交均价）、卖出直接假定全成。**全仓库无一处 `"STOCK","DEAL"` 查询**。

---

## 二、只读定位：调用方与爆炸半径（按授权要求）

### 1. `passorder` 调用点（本文件 3 处，全部为 `ACCOUNT_TAG="b"` 模拟账户）

| 行 | 动作 | 参数 | 后续记账 |
|---|---|---|---|
| L2580 | 卖出·全 | `passorder(24, 1101, ACCOUNT_ID, code, 5, -1, vol, "auction_b", 1, "", C)` | 写锁 + `_log_trade(SELL)` + `position_map.pop` |
| L2619 | 卖出·半 | `passorder(24, ...half...)` | 写锁 + `_log_trade(SELL)` + `shares -= half` |
| L2950 | 买入 | `passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares, "auction_b", 1, "", C)` | 写锁 + `position_map[code]=...` + `_log_trade(BUY)` + `today_bought+=1` |

### 2. 相关函数与调用方（改前须评估）

| 函数 | 行 | 被谁调用 | 是否共享 |
|---|---|---|---|
| `_do_sell` | ~L2560 | `_check_sell` 各分支、`_rotation_sell` | 本文件内；live/tdx 有**各自副本**（同名不同文件） |
| `_do_sell_half` | ~L2598 | peel / 分批止盈路径 | 同上 |
| `_check_buy` | ~L2694 | 主回调 | 本文件 |
| `_sync_holdings` | L994 | 主回调（周期 + run_count==0） | 本文件 |
| `_diag_today_orders` | L973 | 仅 `_sync_holdings` run_count==0 | 本文件 |
| `_mark_order_locked` / `_order_locked` | ~L3010 | 买/卖/对账 | 本文件 |

**爆炸半径结论**：三个 `passorder` 点均在**自包含**的 track_b sim 文件内，不存在被 live 侧 import 的共享函数（各 QMT 文件按项目惯例各自独立）。⇒ 在 sim 内改，**不影响 live / track_a / TDX**，符合红线。

**同模式的其他文件（本次只报不改）**：`TrackB_..._live.py`、`_live_v2.6-tpl.py`、`TrackB_..._tdx_auction_sim.py`、`TrackB_..._v2.6.py`、`track_a/TrackA_..._{sim,live}.py` 均为同一 3 点模式。若 Fix C 在 sim 验证有效，建议后续单开 ticket 评估是否同步 live（需老板单独拍板，红线）。

---

## 三、建议设计（最小、fail-safe、可离线测）

### 新增 1 个纯函数 + 1 个确认器

```
def _order_snapshot(code):        # 读 ORDER+DEAL，返回该 code 当日委托/成交快照
    # ORDER: m_strOrderSysID / m_nOrderStatus / m_nVolumeTotalOriginal / m_nVolumeTraded
    # DEAL : m_strOrderSysID / m_nVolume / m_dPrice   (成交均价)
    return {"sys_ids": {...}, "status": {...}, "filled_vol": int, "avg_px": float}
```

### 落点改动（仅"确认"语义，不引入新交易逻辑）

1. **买入**（L2950 后）：`ret==0` 后调用 `_order_snapshot(code)`：
   - 已 `Filled` → 用 **DEAL 实际成交量/均价** 写 `position_map`（价不再是信号价）；
   - `Pending/PartFilled` → 写 `pending=True` + `order_ref`，**不记 SELL/BUY 成交日志**（改为 `[PENDING]` 日志），等 `_sync_holdings` 下一轮确认；
   - `Canceled/Invalid/不存在` → 打印 `[GHOST] buy not acknowledged`，**回滚**：不写 position、不写锁、不增 `today_bought`。
2. **卖出**（L2580 / L2619）：同样先确认再 `position_map.pop` / 减股数；未确认时**不 pop**、不记 SELL，仅写锁并打 `[PENDING]`，由对账兜底。
3. 新增开关 `VERIFY_FILL = True`（可回退旧行为），便于 sim 一日对照。

### 为什么这样最小
- 不新增交易决策，只把"假定成交"改为"确认成交"，失败侧一律 fail-safe（不记账/保槽），与 Fix A 同风格；
- `_sync_holdings` + POSITION 已是权威对账层，Fix C 只是**把同一权威提前到下单点**，不另建账本。

---

## 四、验收标准（Fix D 式，先红后绿）

新建 `_test_order_confirm.py`（stub `passorder` + stub `get_trade_detail_data("ORDER"/"DEAL")`）：
1. **买入 ret==0 但 ORDER 状态 Canceled** ⇒ 断言 `position_map` 无该票、order lock 无该票、trade_log 无 BUY（改前红）；
2. **买入 Filled，成交均价 ≠ 信号价** ⇒ 断言 `buy_price == DEAL 均价`、`shares == DEAL 量`；
3. **卖出 ret==0 但未成交** ⇒ 断言 `position_map` 仍保留、trade_log 无 SELL；
4. **卖出 Filled** ⇒ 正常 pop / 减股数（回归不破）；
5. `VERIFY_FILL=False` ⇒ 完全回退旧行为（对照用）。

---

## 五、待 WB 确认的开放问题（阻塞落码）

1. **QMT 字段名核验**：sim 环境 `ORDER` 对象的成交量字段是 `m_nVolumeTraded` 还是 `m_nVolumeTotalTraded`？`DEAL` 的均价字段是 `m_dPrice` 还是 `m_dTradedPrice`/`m_dAveragePrice`？（需在 QMT sim 里打印一次真实对象字段，我可出探针脚本）——**字段名错会静默取默认值，必须实测**。
2. **确认时延**：`passorder` 后同 bar 内查询能否立即看到 ORDER 记录？若不能，确认是否需要"次 bar 复核"（这会改变买入时点语义，需你拍板）。
3. **pending 期间是否占用 `MAX_HOLDINGS` 槽**：现 `_sync_holdings` 是"保槽"（防超买）。Fix C 保持一致？
4. **是否同时同步到 live**：按红线本次不做；若你要一并评估，请单独拍板。

---

## 六、产物

- 本 ticket：`bt_research/FixC_ghost_ledger_ticket.md`
- 落码后：`TrackB_..._sim.py` v2.14 + `_test_order_confirm.py` + CHANGELOG + 独立 commit（与 Fix A 分开）
