## 【订正 §① hash + 账户配置对齐】Track B sim ACCOUNT_ID 98009473 → 62128716（Cursor 09-12 11:3x）

前帖 `5638895246` / `5643083186` 给的 md5 需订正，原因是**在 Fix A 之上又对齐了一处配置**。

### 一、账户事实（老板 09-12 明确）
| 账号 | 用途 |
|---|---|
| `98009473` | **轨道 A 模拟** |
| `62128716` | **轨道 B 模拟**（09-11 周五首日） |
| `8886269286` | **实盘** |

### 二、发现：`track_b sim` 的 `ACCOUNT_ID` 指向的是轨道 A 账户
`TrackB_track_b_qmt_auction_sim_v2.13.py` L232 原为 `ACCOUNT_ID = "98009473"  # TODO: change to Track B's separate SIM account`。

关键点：`passorder(23, 1101, ACCOUNT_ID, ...)` 与 `get_trade_detail_data(ACCOUNT_ID, ...)` 用的是**硬编码常量**，**QMT 策略配置里绑定的账号不会覆盖它**。⇒ 若沿用 98009473，Track B 的委托会落进**轨道 A 的模拟账户**，两轨持仓互相污染（`_sync_holdings` 会把对方持仓认作自己的）。

老板部署件已手动改为 `62128716`，仓库此前未同步（违反仓库-first）→ 本次**回写对齐**（提交 `cf0262e`，仅配置、**不升版本号**，仍 v2.13）。

### 三、§① hash 订正（**当前权威值**）
| 文件 | md5 (CRLF) | 说明 |
|---|---|---|
| `track_b/TrackB_track_b_qmt_auction_sim_v2.13.py` | **`a972e0a55dd12694f794a3f56176fed1`** | v2.13 + ACCOUNT_ID=62128716（= 老板部署件） |
| 上值（仅 ACCOUNT_ID 不同，作废） | `1da96de8636cb9b5f014bda1ad8812ef` | v2.13 + ACCOUNT_ID=98009473 |
| LF 行尾变体 | `6dfe7fb054f4a5616e210c60bb865089` | 内容等价 |

部署件老板已含 `track-B v2.13` 与 `money_pass all rejected -> flat` 两标记 ⇒ 放行条件 ① 以**部署件=仓库(62128716 版)** 达成。

### 四、顺手修 CHANGELOG
`production_strategies/CHANGELOG.md` 有 3 处条目标题在早前编辑中丢失（v2.39→v2.40、LIM10、K线 兜底），已补回，条目顺序恢复正常。

### 五、对 Fix C 的影响
Fix C 的 `_order_snapshot` 必须查**下单去的那个账户**，故先定稿 `ACCOUNT_ID=62128716`（已完成），Fix C 落码时直接复用该常量。Fix C 仍阻塞在 **QMT ORDER/DEAL 字段名实测**（探针已含类反射，无需成交单）。

—— Cursor
