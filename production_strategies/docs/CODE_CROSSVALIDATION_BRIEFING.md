# 双轨策略代码交叉验证简报（供 DeepSeek Harness 逐行核对 6 个策略文件）

> 版本：v1.0
> 日期：2026-08-16
> 作者：AlphaPilot 主控 Agent
> 读者：**DeepSeek Harness**（全新 Agent，无本项目任何上下文）
> 用途：本文档是**代码级交叉验证任务书**。上一轮已对"设计"做过交叉验证（见 `DUAL_TRACK_BRIEFING.md`，结论已落实进代码）。本轮验证对象是 **6 个已落地的策略文件**，任务 = 逐行读代码，找出逻辑错误 / API 误用 / 平台差异 bug / 轨道 A↔B 不一致 / 回归风险。
>
> **工作方式**：所有文件都在本地 `C:\Users\elvisq\Projects\alphapilot\`，请直接读取源代码逐行核对，不要依赖本文描述。本文只是导航 + 任务清单 + 已知背景，**文中任何陈述都可能与代码不符——以代码为准**。

---

## 1. 背景（最短版）

- 服务器（`/home/ubuntu/alphapilot/`，24/7）：
  - 05:00 全市场选股管线 → `daily_recommend.json` 的 `recommendations`（≤500 只，8/14 为 135 只）
  - 06:30 `export_qmt_scores.py --fullpool` → `output/qmt_scores/{date}.fullpool.json`（全量候选池，轨道 B 数据源）
  - 09:36 `export_qmt_scores.py` → `{date}.json` + `{date}.candidates.json`（轨道 A 数据源）
  - nginx 静态托管 `/qmt_scores/` → `http://150.158.100.236/qmt_scores/{date}*.json`
- 本地两个交易端：QMT（国金）+ TdxQuant 通达信，各跑 Python 策略，从服务器拉分数文件 → 盘中确认 → 下单。

**双轨**：
- **轨道 A（现有，不动）**：读 Top10 candidates → P2 动态确认 → Top2 买入 → 卖出。
- **轨道 B（新增）**：读全量 fullpool → **09:25-09:35 QMT/TDX 端自己做门控选股**（P0 硬过滤 → P1 竞价门控 → P2 资金门）→ Top2 买入 → 卖出复用轨道 A 逻辑。

---

## 2. 待验证文件清单（6 个）

| # | 文件（绝对路径） | 版本 | 平台/盘型 | 角色 |
|---|-----------------|------|-----------|------|
| 1 | `C:\Users\elvisq\Projects\alphapilot\qmt_model_full_chain_v2.py` | v2.12 | QMT **模拟盘** | 轨道 A 模拟权威版 |
| 2 | `C:\Users\elvisq\Projects\alphapilot\qmt_model_full_chain_template.py` | v2.12-tpl | QMT **实盘** | 轨道 A 实盘模板（每账户一份） |
| 3 | `C:\Users\elvisq\Projects\alphapilot\tdx_full_chain.py` | v2.10 | TDX **模拟盘** | 轨道 A TDX 版 |
| 4 | `C:\Users\elvisq\Projects\alphapilot\track_b_qmt_auction_sim.py` | v1.0 | QMT **模拟盘** | 轨道 B QMT 竞价选股 |
| 5 | `C:\Users\elvisq\Projects\alphapilot\track_b_qmt_auction_live.py` | v1.0-tpl | QMT **实盘** | 轨道 B QMT 实盘模板 |
| 6 | `C:\Users\elvisq\Projects\alphapilot\track_b_tdx_auction_sim.py` | v1.0 | TDX **模拟盘** | 轨道 B TDX 竞价选股 |

**废弃/参考文件（不在验证范围，勿混淆）**：
- `qmt_model_full_chain_live.py` = v2.11-live，**已被 template v2.12-tpl 取代**。
- `qmt_model_full_chain_v1.py` = v1.0，历史版，废弃。
- `tdx_full_chain_v210_friend_12801068.py` = 给朋友账户的 TDX 副本，由 TDX 版改配置生成，不在本轮验证范围（除非你认为需要，请在报告中说明）。

**权威基线判定**：轨道 A QMT 模拟 = #1；轨道 A QMT 实盘 = #2（每账户复制后只改 CONFIG 块）；轨道 A TDX = #3。轨道 B = #4/#5/#6。**注意：sim 与 live 模板之间应是"同一策略 + 配置差异"，TDX 与 QMT 之间应只有"平台 API 差异"。**

---

## 3. 每个文件的关键逻辑块（验证时对照）

### 3.1 轨道 A QMT 模拟盘 `qmt_model_full_chain_v2.py`（1555 行）

- `init` / `handlebar`（1 分钟粒度）。
- 数据：本地 `C:/alphapilot/scores/{date}.candidates.json`（Top10）→ 缺则 `{date}.json` → 缺则远程 nginx。
- 买入 `_check_buy`：按 rank 逐个 P2 动态确认（趋势 c>P935 且 c>VWAP；近 2 根 5m 量比>1.3 且收阳；不追高 c≤昨收×1.08）→ 先到先得 → `passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares, "fullchain", 1, "", C)`（quickTrade=1）。
- 卖出 `_check_sell`：T+1 保护 → 跌停可卖 → Wyckoff/VWAP 早出 → 自适应止损 → T+2 强平 → 动态分批。
- 订单锁 `order_locks.json` 文件级防重；**拒单不写锁**（v2.11 修复）。
- `_sync_holdings` 用 `m_nCanUseVolume` 写 `pos["can_use"]`，卖出封顶 can_use（v2.12 修复"可用数量不足"）。

### 3.2 轨道 A QMT 实盘模板 `qmt_model_full_chain_template.py`（约 1480 行）

- 与 v2.12 **共享同一套策略逻辑**，头部 CONFIG 块参数化（ACCOUNT_ID / ACCOUNT_NAME / ALLOW_STAR / ALLOW_CHINEXT / ALLOW_BSE / POSITION_PCT）。
- 文件底部有 `HOW TO USE THIS TEMPLATE` README。
- **重点核对**：模板化是否引入了与 v2.12 不一致的行为（例如 ACCOUNT_TAG 路径隔离、日志标识、`passorder` 实盘参数）。

### 3.3 轨道 A TDX `tdx_full_chain.py`（1527 行）

- 平台 API 差异：`tq.get_market_snapshot`（Now/LastClose/Open/Max/Min/Volume/Average/Before5MinNow）、`tq.get_market_data`（1m/5m/1d，pandas DataFrame）、`tq.order_stock`、`tq.query_stock_asset`、`tq.query_stock_positions`。
- P2 确认：5m bars 完整版，分钟线不可用时降级为快照确认。
- 卖出同 QMT v2.12（自适应止损/peel/T+2/VWAP/Wyckoff/跌停保护）。
- **注意**：此文件含中文注释（TDX 独立运行无 QMT 加密问题，UTF-8 合法）。
- **重点核对**：TDX 的 `order_stock` 拒单判定（int<0 或 dict ErrorId!=0）是否正确；成交量单位换算（snapshot Volume 手 ×100 vs 1d Volume 股）是否一致。

### 3.4 轨道 B QMT 模拟 `track_b_qmt_auction_sim.py`（约 1550 行）

- `ACCOUNT_TAG = "b"` → 本地文件全部 `b_` 前缀（`b_trades_fullchain.json` / `b_ledger_daily.json` / `b_order_locks.json` / `b_auction_gate.json`）。
- 数据源 = `{date}.fullpool.json`（全量候选，非 Top10）。
- 门控流程（1 分钟 handlebar）：
  - P0 硬过滤：板块权限 / 涨停封死 / 停牌无数据 / 竞价量≤0。
  - P1 竞价门控 `_p1_gate`：gap≥9% 淘汰 / gap<-2% 淘汰 / gap<0 且板块弱 淘汰 / gap<-0.5% 降权 / 否则加分；板块分散 Top10≤2、Top20≤3、全池≤5；**板块聚合用 QMT 本地 `get_stock_list_in_sector` 全成分股**（`_sector_constituents`）；迟到数据截止 `CALL_DATA_CUTOFF=09:30`。
  - P2 资金门 `_p2_gate`：主动买占比≥0.52（tick 近似，仅 09:30 后）/ 换手 2~35% / 量比≥0.8 / 跌幅≥-5% / 主力5日净流入≥0（fullpool 预置，0=缺数据跳过硬门）。
  - 排序 → Top2（money_pass 优先，再按 score_0500 降序）→ `passorder` 买入。
- 卖出 = 复用 v2.12 逻辑。
- **重点核对**：`_get_active_buy_ratio` 的 tick 近似算法（成交价≥卖一=主动买）是否与 `get_market_data_ex(period="tick")` 字段匹配；板块聚合的性能与正确性；`_update_auction_state` 的 gap 缓存与 09:30 截止语义。

### 3.5 轨道 B QMT 实盘模板 `track_b_qmt_auction_live.py`（约 1670 行）

- 与 #4 同一逻辑，头部 CONFIG 参数化（ACCOUNT_ID 占位 `"8886269286"`、ACCOUNT_TAG=`"b_live"`、权限开关默认全 False），底部 README。
- **重点核对**：#4 与 #5 除配置外逻辑是否完全一致；实盘参数（如 passorder 价格类型、撤单、日志）是否适合实盘。

### 3.6 轨道 B TDX 模拟 `track_b_tdx_auction_sim.py`（约 1650 行）

- 独立运行（`main()` + `while True` 主循环 `POLL_SEC=20`），非 QMT handlebar。
- 数据源 = `{date}.fullpool.json`，缺失时 `_fetch_remote_fullpool` 从 nginx 拉（06:30 后，60s 节流）。
- P1：gap 用快照 Open/LastClose；板块聚合**降级**为候选池自身按 `industry_l1` 聚合（TDX 无可靠板块成分接口）。
- P2：主动买占比**降级**为快照盘口委托比 Buy1Vol/(Buy1Vol+Sell1Vol)（软信号，拿不到不硬堵）；换手 = snapshot Volume(手)×100/流通股本；量比 = snapshot Volume(手)/前5日 1d 量均值。
- 卖出 = 复用 #3 TDX v2.10 逻辑。
- **重点核对**：与 #3 的卖出逻辑是否真正一致；与 #4 的 P1/P2 门控规则是否对齐（允许因平台数据差异降级，但**规则阈值/时序必须一致**）；独立主循环的时序（09:25 开始 / 09:30 P2 / 09:35 决策 / 09:40 截止）是否与 QMT 版一致。

---

## 4. 历史已修 Bug（防回归，逐项确认代码中确实已修复）

| # | Bug | 修复版本 | 需确认点 |
|---|-----|---------|---------|
| B1 | 拒单仍写订单锁+持仓+账本+today_bought，导致全天不再买入 | v2.11（所有平台） | 6 个文件的买入路径：`passorder`/`order_stock` 返回被拒时是否**不写锁、不消耗 BUY 名额** |
| B2 | 可用数量不足：内存 shares 过期导致超额卖单被券商拒 | v2.12（QMT） | #1/#2/#4/#5 的 `_sync_holdings` 是否读 `m_nCanUseVolume` 并封顶卖单 |
| B3 | 当日买入股因 `m_strOpenDate` 为空导致 T+1 判定失败 | v2.12（QMT） | #1/#2/#4/#5 的 `buy_date` 推断（can_use<vol → 今日买入） |
| B4 | TDX `order_stock` 被拒返回值被忽略 | TDX v2.10 | #3/#6 的拒单判定（int<0 或 dict ErrorId!=0）且不写锁 |
| B5 | 旧持仓被误算为今日买入，撞满 MAX_DAILY_BUY | TDX v2.9 | #3/#6 的 `_sync_positions` buy_date 仅当 `TodayBuyPosition>0` 才标今天 |
| B6 | 文件损坏/0字节导致买入卡死 | TDX v2.8 | #3/#6 的坏文件自愈（删除重拉） |
| B7 | QMT 加密非 ASCII 导致 SyntaxError | 各版 | 所有 QMT 文件（#1/#2/#4/#5）应**纯 ASCII**；TDX（#3/#6）可含中文 |

---

## 5. 交叉验证任务清单（按优先级）

### P0 · 致命（阻止交易或资金损失）
1. **拒单处理**：逐文件确认买入/卖出的拒单路径不会写锁/假账本/假持仓/占用今日额度（B1）。
2. **卖单封顶**：#1/#2/#4/#5 的卖单 volume 是否 ≤ can_use（B2）。若某文件没有 can_use 机制，请指出——那可能是漏同步。
3. **T+1 保护**：当日买入股是否在任何路径被尝试卖出（B3）；TDX 版 T+1 推断是否可靠。
4. **T+2 强平逻辑**：卖出顺序、强平时间窗口、`t2_extended` 一次性延期语义是否 6 文件一致。
5. **板块权限过滤**：STAR/创业板/北交编码前缀判定在 6 文件中是否一致（300/301、688/689、8xx/4xx/920）。

### P1 · 高（选股/门控正确性）
6. **P1 门控规则对齐**：对比 #4 与服务器 `pre_market_gate.py` 的阈值（GAP_LIMIT_UP=9.0、个股 gap<-2% 不硬踢、GAP_DEMOTE=-0.5、penalty=max(0.05,min(0.35,abs(gap)*0.13))、bonus 档位、弱板块 -3%）；#6 是否同阈值（允许数据源降级，规则不可漂移）。
7. **P2 门控规则对齐**：主动买≥0.52、换手 2~35、量比≥0.8、跌幅≥-5、主力5日净流入硬门（0=跳过）——对比 #4/#6 与服务器 `money_flow_gate.py` 默认参数。
8. **排序与 Top2**：money_pass 优先，再 score_0500 降序；板块分散约束（Top10≤2/Top20≤3/全池≤5）是否生效。
9. **CALL_DATA_CUTOFF=09:30 语义**：09:30 后到的新 gap 只更新缓存不进决策——#4/#6 是否一致实现。
10. **score 口径**：`score_0500 = icir_raw_score → score_raw → ml_score`（服务器 fallback）；QMT/TDX 端是否直接使用，没有再用 `score`/`pre_market_adjusted_score`。

### P2 · 中（平台差异 / 数据正确性）
11. **tick 近似主动买占比**（#4）：`get_market_data_ex(period="tick")` 字段（lastPrice/askPrice1/bidPrice1/volume）是否真实存在；成交量小跳过逻辑是否合理；09:30 前是否确实不启用。
12. **TDX 主动买占比降级**（#6）：Buy1Vol/Sell1Vol 字段名猜测是否与 TDX snapshot 实际字段匹配；软信号语义（拿不到不硬堵）是否符合设计。
13. **换手率/量比口径**：#4（QMT vol/FloatVolume）vs #6（snapshot Volume×100/流通股本）vs 服务器腾讯 turnover——单位换算是否一致（手 vs 股）。
14. **板块聚合**（#4）：`get_stock_list_in_sector` 调用是否真实可用、性能是否可接受（1 分钟粒度）；#6 候选池自身聚合是否有 n=1 失真。
15. **fullpool 字段**：读取 `score_0500`/`main_net_5d`/`industry_l1`/`symbol`/`name`/`rank` 的 key 是否与服务器 `export_qmt_scores.py` 输出一致（用 8/14 或本地样例验证）。

### P3 · 低（稳健性/日志/一致性）
16. **路径隔离**：轨道 A/B 的本地文件（账本/锁/日志）是否完全隔离（b_ 前缀），不会互相覆盖。
17. **远程拉取**：`_fetch_remote_fullpool`/`_fetch_remote_scores` 的节流、超时、坏文件自愈是否健壮。
18. **日志**：`[INIT]`/`[CAND]`/`[BUY]`/`[SELL]`/`[WAIT]`/`[LOCK]`/`[FETCH]` 标识是否足够诊断；今日额度/锁摘要是否在 INIT 打印。
19. **每日重置**：换日时 gap 缓存、sent_today、p1_survivors、top2_fired、gate_dump_done 是否重置。
20. **QMT ASCII**：#1/#2/#4/#5 是否纯 ASCII（无中文/emoji/全角字符）。

---

## 6. 交付物格式

请输出 Markdown 报告，包含：

1. **结论总表**：每文件一行（语法/ASCII/平台 API/逻辑正确性/与设计一致性），标 ✅ / ⚠️ / ❌。
2. **发现清单**：按 P0/P1/P2/P3 分组，每条含【文件:行号】【问题描述】【证据（引用代码）】【建议修复】。
3. **轨道 A↔B 差异清单**：6 文件之间的任何不一致（阈值、时序、逻辑、字段）。
4. **与设计简报 `DUAL_TRACK_BRIEFING.md` 的偏离**：哪些已落实、哪些代码与设计冲突。
5. **风险排序**：你认为最可能导致"买不进/卖不出/买错股"的前 3 项。

---

## 7. 补充材料（如需要）

- 服务器 06:30 fullpool 导出：`export_qmt_scores.py`（含 `--fullpool`）——本地文件在 `C:\Users\elvisq\Projects\alphapilot\export_qmt_scores.py`，服务器版已同步。
- 服务器门控基线：`pre_market_gate.py` / `morning_live_fund_select.py` / `money_flow_gate.py` 在本地项目根目录有副本可读。
- 设计交叉验证报告：`DUAL_TRACK_BRIEFING.md`（上一轮设计级验证，本轮以代码为准）。
- 离线测试：#4/#6 有 `_test_tdx_b.py` 等 mock 测试脚本（`tqcenter_test.py`），可参考但**不代表真实平台验证**。
