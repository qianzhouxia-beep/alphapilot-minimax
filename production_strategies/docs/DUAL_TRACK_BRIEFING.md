# 双轨并行选股 · 完整方案简报（供 DeepSeek Harness 交叉验证）

> 版本：v2.1（已应用 DeepSeek Harness 交叉验证修正）
> 日期：2026-08-16
> 作者：AlphaPilot 主控 Agent
> 读者：**DeepSeek Harness**（全新 Agent，无本项目任何上下文）
> 用途：本文档是**自包含简报**——从背景、来龙去脉、现状到新方案设计、待办任务、验证问题，全部在此。读完本文即可独立交叉验证，无需访问服务器或历史对话。
>
> **验证任务**：逐条核对轨道 B 设计是否与轨道 A 现有实现一致、逻辑是否自洽、有无遗漏或歧义、数据源是否真实可得。

---

## 目录

1. [背景与来龙去脉](#1-背景与来龙去脉)
2. [系统总架构](#2-系统总架构)
3. [轨道 A 完整现状（权威基线，已逐行核实）](#3-轨道-a-完整现状权威基线已逐行核实)
4. [轨道 B 设计方案（新增）](#4-轨道-b-设计方案新增)
5. [待办任务清单](#5-待办任务清单)
6. [待交叉验证的问题清单（重点）](#6-待交叉验证的问题清单重点)
7. [关键代码出处与文件清单](#7-关键代码出处与文件清单)

---

## 1. 背景与来去脉

### 1.1 这是什么系统

一套**A 股量化选股 + 自动交易**系统，分两部分：

1. **服务器端**（`/home/ubuntu/alphapilot/`，24/7 运行）：
   - 每天 05:00 跑全市场选股管线（形态扫描 + 多道门控 + 机器学习打分 + LLM 审计），产出候选池。
   - 09:25-09:35 盘中阶段对候选池做集合竞价门控、实时资金流重排、最终选 Top2。
   - 把结果导出成 JSON 文件，通过 nginx 静态托管。
2. **本地 QMT 交易端**（Windows，`C:\alphapilot\scores\`）：
   - 跑 Python 策略，从服务器拉取分数文件，按排名做盘中动态确认后自动买卖。
   - 分模拟盘和实盘两套账户，策略分别部署。

### 1.2 关键演进历史（为什么会有今天的方案）

| 阶段 | 发生了什么 |
|------|-----------|
| 早期 | QMT 策略直接按服务器给的 Top2 下单，无盘中确认。 |
| v2.x 演进 | 加入 P2 盘中动态确认（趋势/量能/不追高），买入前逐票验证。修复多个 bug：拒单误写订单锁（v2.11）、可用数量不足导致卖单被拒（v2.12）、订单锁防重、`can_use` 封顶。 |
| TDX 分支 | 为朋友的 TdxQuant 通达信环境写了独立版本，逻辑与 QMT 版对齐。 |
| **当前（本次任务）** | 用户提出**双轨并行**：轨道 A（现有链路，不动）保留；新增轨道 B（QMT 端独立选股）做对比与保底。 |

### 1.3 用户的核心诉求（原文要点，务必精确理解）

1. **轨道 A 保持不变**，新增轨道 B，两套并行跑在**两个独立 QMT 模拟账户**上，用于比较与保底。
2. 轨道 B 的选股逻辑：**09:25-09:35 集合竞价阶段，QMT 对 5 点管线选出的【全部候选】做门控选股**，选 Top2 后下单。
3. 轨道 B 的 09:25-09:35 选股策略，**与轨道 A 在服务器上 09:25~09:35 的策略一致**。
4. QMT 算不了的数据（如主力 5 日净流入），由**服务器预置**进 fullpool 文件。
5. 账户无 Level2 权限（贵，6000+/年），主动买占比用 **tick 近似**实现。

### 1.4 已核实的重要事实（容易搞错，务必记住）

- 09:35 的"重新评分"在 **pipeline ≥ 100** 时是从 **05:00 生成的股票池**里做的，不是重新跑全市场管线。
- 05:00 管线输出候选数**不固定**：最多 500 只，弱市可能只有 4 只（8/25），取决于门控淘汰。**不凑 100**。
- **pipeline < 100** 时走 **涨幅 Top~1000 资金轨**（`momentum_top1000_fund_flow`），看当日热点；弱市/降仓**仍启用**（2026-08-25 用户定案，2026-08-28 恢复部署）。详见 `knowledge/strategies/0935_momentum_scanner.md`。
- 09:25 竞价门控轨道 A 只处理候选池 **Top100**，其余候选原样保留。
- 轨道 B 要求对**全部候选**（非 Top100）做门控，这是与轨道 A 的关键区别。

---

## 2. 系统总架构

```
┌─────────────────── 服务器（24/7） ───────────────────┐
│ 05:00  alphapilot_pipeline_v3.py                     │
│        全市场 4991 只 → 形态扫描+门控+ML+LLM          │
│        输出 daily_recommend.json 的 recommendations   │
│        （≤500 只，8/14 实为 135 只）                  │
│                                                       │
│ 09:25  pre_market_gate.py                            │
│        对 Top100 做集合竞价门控                        │
│        写回 recommendations（含 pre_market_* 字段）    │
│                                                       │
│ 09:35  live_momentum_scanner.py                      │
│        ≥100: 池内 0.6/0.4 重排                       │
│        <100: 涨幅 Top~1000 资金轨（弱市仍启用）       │
│        recommendations=Top50                          │
│                                                       │
│ 09:35  morning_live_fund_select.py                    │
│        资金门 + 研究门 → Top2 正式推荐 + Top10 候选     │
│                                                       │
│ 09:36  export_qmt_scores.py                           │
│        导出 {date}.json + {date}.candidates.json      │
│        （★新增：导出 {date}.fullpool.json 供轨道 B）   │
│                                                       │
│ nginx 静态托管 /qmt_scores/                            │
└───────────────────────────────────────────────────────┘
                        │ HTTP 拉取
                        ▼
┌─────────────────── 本地 QMT 交易端 ───────────────────┐
│ 轨道 A：qmt_model_full_chain_v2.py (v2.12)            │
│   读 candidates.json(Top10) → P2确认 → Top2 买入      │
│   卖出：T+1保护/止盈止损/T+2强平/动态分批              │
│   模拟账户 A                                          │
│                                                       │
│ 轨道 B：qmt_auction_select_v1.py（★新增，本次设计）   │
│   读 fullpool.json(全量候选)                           │
│   09:25-09:35 QMT 端门控选股 → Top2 买入              │
│   卖出：复用 v2.12 卖出逻辑                            │
│   模拟账户 B                                          │
└───────────────────────────────────────────────────────┘
```

---

## 3. 轨道 A 完整现状（权威基线，已逐行核实）

### 3.1 服务器端链路（按时序）

| 时点 | 脚本 | 输入 | 动作 | 输出 |
|------|------|------|------|------|
| 05:00 | `alphapilot_pipeline_v3.py` | 全市场 4991 只 | 形态扫描+多道门控+ML+LLM+S2 | `output/daily_recommend.json` 的 `recommendations`（≤500 只，8/14 实为 135 只） |
| 09:25 | `pre_market_gate.py` | `recommendations` | 对 **Top100** 做集合竞价门控 | 写回 `recommendations`（含 `pre_market_*` 字段） |
| 09:35 | `live_momentum_scanner.py` | `full_candidate_pool` 或 `recommendations` | **≥100**：池内 0.6 管线 + 0.4 动量重排；**<100**：涨幅 Top~1000 资金轨（ICIR+动量+门控） | `recommendations`=Top50；protocol 见下表 |
| 09:35 | `morning_live_fund_select.py` | `recommendations` | 资金门+研究/板块门 | Top2 正式推荐 + Top10 候选池 |

#### 3.1a 09:35 scanner 双路径（2026-08-25 定案，勿改语义）

| 条件 | 函数 | protocol | 说明 |
|------|------|----------|------|
| N ≥ 100 | 池内重排 | `live_momentum_from_pipeline_500` | 全市场 akshare 仅作动量 z 基准 |
| N < 100 | `_momentum_top1000_scan` | `momentum_top1000_fund_flow` | 涨跌幅 Top~1000，非全 5000；弱市仍走 |
| 文件缺失 | `_momentum_top1000_scan(None)` | 同上 | daily_recommend 不可读时的兜底 |

完整规则：`knowledge/strategies/0935_momentum_scanner.md`；Agent 约束：`.cursor/rules/live-momentum-scanner.mdc`。
| 09:36 | `paper_trading_signals.py` + `trade_executor.py` | `recommendations` | **服务器端纸面交易**（读 `data/paper_trading.json`，模拟成交） | 纸面持仓/信号（⚠️ 非 QMT 下单，但也在 09:36 跑，需与轨道 B 区分） |
| 09:36 | `export_qmt_scores.py` | `recommendations` | 导出 | `{date}.json`（全评分）+ `{date}.candidates.json`（Top10） |
| ↓ | nginx `/qmt_scores/` | | 静态托管 | |
| 全天 | `qmt_model_full_chain_v2.py` (v2.12) | 本地 `C:/alphapilot/scores/` | 按 rank P2确认买入、卖出 | 模拟盘交易 |

### 3.2 09:25 竞价门控精确规则（`pre_market_gate.py`）

**输入**：`recommendations` 前 **Top100**（`CALL_AUCTION_TOP_N = 100`，L42）。
**个股竞价信号**：`compute_stock_signals(q)` → `gap_pct = (open_px / prev_close - 1) × 100`，另取竞价金额/量。
**板块聚合**：`aggregate_sector_signals(quotes, industry_map)`（L164）→ 按 `industry_l1` 对候选聚合 `gap_mean`、`neg_ratio`、`sector_weak`（`gap_mean < -1.5%` 判弱）。**聚合对象 = 候选池（Top100），非全市场。**
**板块分散**：`enforce_sector_diversity`（L190）→ Top10 同板块≤2，Top20 同板块≤3，全池同板块≤5。

**门控规则**（逐条，按优先级，`pre_market_gate.py:338-402`）：

| 规则 | 条件 | 动作 |
|------|------|------|
| 无竞价数据 | `sig is None` | 保留但 score × 0.95（降权 5%） |
| 规则1 近涨停 | `gap_pct ≥ GAP_LIMIT_UP = 9.0`（L45/L341） | 淘汰 |
| 规则2 gap 过低 | ~~`gap_pct < -2.0` 淘汰~~（2026-08-22 已撤） | 改走规则4降权 |
| 规则3 双重弱 | `gap_pct < 0` 且 所在板块 `sector_weak` | 淘汰 |
| 规则4 降权 | `gap_pct < GAP_DEMOTE = -0.5` | score × (1 - penalty)，`penalty = max(0.05, min(0.35, abs(gap)×0.13))` |
| 规则5 保留 | `gap_pct ≥ -0.5` | 加分：gap≥2% +6%，gap≥0.5% +3%，gap≥0 +1%，否则 0；弱板块额外 -3% |

**写回**：`final_pool` + 未参与竞价的 `items[100:]` 合并，`recommendations = merged_pool`（保持池完整供 09:35 用）。

### 3.3 09:35 资金门精确规则（`money_flow_gate.py`）

**数据源**：`enriched_data.get_quotes_batch` → 腾讯行情 `qt.gtimg.cn`。
**函数默认参数**（L15-19）：
```
min_active_buy = 0.52     # 主动买占比下限
min_turnover   = 2.0      # 换手率下限 %
max_turnover   = 35.0     # 换手率上限 %
min_vol_ratio  = 0.8      # 量比下限
max_drop_pct   = -5.0     # 当日最大跌幅 %
hard_main_net_5d = False  # 默认关，生产开启
```
**资金门判定**（L74-79）：
```
money_pass = (abr ≥ 0.52) AND (2.0 ≤ turnover ≤ 35.0) AND (vr ≥ 0.8)
然后：chg < -5.0% → money_pass = False（当日跌幅超阈值）
```
**硬门**：生产调用 `apply_money_flow_gate(pool, top_n=None, hard_main_net_5d=True)`（`morning_live_fund_select.py:456`）→ 读 `data/fund_flow_history.json`（东财历史资金流），取最近 5 日净流入求和，`sum < 0` → 硬剔。
**基本面门**：`check_fundamentals` → mootdx 财报。

### 3.4 09:35 排序选 Top2（`morning_live_fund_select.py`）

- 生产默认 `MORNING_RANK_MODE=model`（L35-36）→ `select_top_by_score`（L268-292）：
  1. `passed = [r for r in gated if money_flow_pass is True]`
  2. `pool = passed if passed else list(gated)`（资金门通过者优先）
  3. `sorted(pool, key=score_of, reverse=True)[:2]`（`LIVE_TOP_N=2`，L32）
  4. `score_of` 含二次微调：`score × (1 + (book_price_quantile_250 - 0.5) × BOOK_RERANK_STRENGTH)`。**⚠️ `BOOK_RERANK_QUANTILE` 默认开启**（`morning_live_fund_select.py:44-48`，env 默认 `"1"`，强度 `0.10`；需 `BOOK_RERANK_QUANTILE=0` 才关闭）。轨道 B 需决定是否复刻此微调。
- `fund` 模式：`select_top_by_inflow` = 主动买占比 + 主力净流入排序。
- 8/14 实况：`recommendations` 44 只、`full_candidate_pool` 83 只，最终 Top2 = 002582 好想你、000938 紫光股份。

### 3.5 QMT 端全链策略 v2.12（`qmt_model_full_chain_v2.py`）

**数据读取**：`{date}.candidates.json`（Top10 候选池）→ 缺则 `{date}.json` 前 10 → 缺则远程 nginx。
**买入流程**：
- 按 rank 逐个 P2 确认 → 先到先得。
- P2 动态确认（L894-972）：趋势 `c > P935` 且 `c > VWAP`；量能 近 2 根 5m 量比 > 1.3 且收阳；不追高 `c ≤ 昨收 × 1.08`。
- 下单 `passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares, "fullchain", 1, "", C)`（L1317-1351，quickTrade=1 即时）。
- 仓位 = `int(total_asset × 0.15 / fill / 100) × 100`，封顶可用现金。
- 订单锁 `order_locks.json` 文件级防重；**拒单不写锁**（v2.11 修复）。

**卖出流程**（L976-1101）：
- T+1 保护 → 跌停可卖 → Wyckoff/VWAP 早出 → 自适应止损 → T+2 强平 → 动态分批。
- `can_use` 封顶（v2.12 修复，防"可用数量不足"）。

---

## 4. 轨道 B 设计方案（新增）

### 4.1 分工边界

| 环节 | 执行者 | 说明 |
|------|--------|------|
| 05:00 全门控候选池 | **服务器** | 现有 pipeline 已产出 `daily_recommend.json` |
| fullpool 导出 | **服务器**（新增） | `export_qmt_scores.py` 末尾追加，导出完整候选池 |
| 09:25-09:35 门控选股 | **QMT Python**（新增策略） | 对全部候选做竞价门控+资金门+排序 |
| Top2 下单 | **QMT Python** | passorder quickTrade=1 |
| 卖出 | **QMT Python** | 复用 v2.12 卖出逻辑 |

**关键**：服务器只做到"导出 fullpool"，不再做 09:25/09:35 的选股（那是轨道 A 服务器做的事）。轨道 B 的选股全部在 QMT 端完成。

### 4.2 服务器改动（增量，不碰现有）

**导出时机**（采纳交叉验证建议）：新增 cron `06:30` 跑 `export_qmt_scores.py --fullpool`，读 **05:00** `daily_recommend.json` 的 `recommendations`（纯静态池，不含 09:35 资金流重排）。

`export_qmt_scores.py` 末尾追加 `_export_fullpool()`：

```
full_pool = rec.get("recommendations") or rec.get("full_candidate_pool") or []
rows = []
for each in full_pool:
    score = icir_raw_score
         or score_raw            # icir_raw_score 为 None 时（未竞价门控的股票）
         or ml_score             # 再回退
    rows.append({
        symbol, name, rank, industry_l1,
        score_0500=score,        # 统一 score 口径（见 §4.5）
        main_net_5d,             # 预置；可能为 None 时置 0 或跳过资金硬门
        pre_market_*             # 不导出（QMT 独立重算）
    })
写 output/qmt_scores/{date}.fullpool.json
```

**关键修正**：
- `icir_raw_score` 有 **8/44 None**（`recommendations`）→ 必须 fallback。
- `main_net_5d` 在 `full_candidate_pool` **83/83 全 None** → 若导出 06:30 的 `recommendations`，需确认其 `main_net_5d` 完整；不完整则轨道 B 资金门**跳过该硬门**（降级为软信号）。
- `pre_market_*` 字段**不导出**（06:30 时 09:25 门控尚未跑），QMT 端独立重算。

### 4.3 QMT 轨道 B 策略 `qmt_auction_select_v1.py`（新增）

**数据源**：
- fullpool：本地 `C:/alphapilot/scores/{date}.fullpool.json`，缺则远程 nginx。
- 实时行情：QMT `get_market_data_ex(period="tick"/"1m"/"5m"/"1d")` + `get_full_tick`。
- 合约信息：`get_instrument_detail`（PreClose/UpStopPrice/FloatVolume）。
- 板块：`get_stock_list_in_sector` / `get_industry`（QMT 本地，用于板块聚合）。

**时间线**：

```
[09:00 前] 拉取 fullpool，订阅行情（持仓+全部候选）
[09:25-09:30] 对【全部候选】拉集合竞价行情，算 gap_pct
[09:25-09:35 每 tick/每 1m] 逐候选跑门控（P0→P1→P2）
[09:35] 选 Top2 → 下单
[09:30-14:57] 卖出逻辑（复用 v2.12）
```

**门控流程**（对齐轨道 A 规则，但对象=全部候选；**1 分钟 handlebar 粒度**）：

```
P0 硬过滤（每日一次）:
  - 板块权限不符 → SKIP
  - 涨停价封死（现价 ≥ UpStopPrice×0.997） → SKIP
  - 停牌/无数据 → SKIP
  - 竞价量 ≤ 0 → SKIP

P1 竞价门控（09:25-09:30，对齐 pre_market_gate 规则）:
  - gap ≥ 9.0%（近涨停） → 淘汰
  - gap < -2.0% → 不再淘汰（2026-08-22，走降权）
  - gap < 0 且 板块弱 → 淘汰
  - gap < -0.5% → score×(1-penalty)，penalty=max(0.05, min(0.35, abs(gap)×0.13))
  - gap ≥ -0.5% → score×(1+bonus)，bonus=gap≥2%?0.06:gap≥0.5%?0.03:gap≥0?0.01:0，弱板块-3%
  - 板块分散（Top10≤2, Top20≤3, 全池≤5）【用 QMT 本地全板块成分股聚合】
  - 迟到数据截止 CALL_DATA_CUTOFF=09:30（09:30 后到的新 gap 只更新，不进决策）
  排序 → 取前 N（如 Top50）

P2 资金门（09:30-09:35，对齐 money_flow_gate;【竞价时段失真 → 09:30 前不启用】）:
  对 P1 幸存者：
  - 主动买占比 ≥ 0.52（tick 近似，连续竞价段才有效，见 §4.4）
  - 2.0% ≤ 换手率 ≤ 35%
  - 量比 ≥ 0.8
  - 当日跌幅 ≥ -5%
  - 主力 5 日净流入 ≥ 0（fullpool 预置；缺则跳过硬门降级软信号）
  排序 → Top2（资金门通过者优先，再按 score_0500 降序）
```

> ⚠️ **性能约束**：交叉验证结论 = 1 分钟粒度可行、tick 粒度不可行。QMT 策略用 **1 分钟 handlebar** 驱动，每周期对幸存候选批量拉 tick/1m 计算；tick 订阅仅用于持仓监控，不做全池扫描。

### 4.4 主动买占比：tick 近似（账户无 Level2）

账户未开通 Level2（6000+/年），用免费 tick 近似：

```
对每只候选拉 get_market_data_ex(period="tick", count=N) 分笔：
  单笔成交价 ≥ 卖一价(askPrice1) → 记主动买
  单笔成交价 ≤ 买一价(bidPrice1) → 记主动卖
  成交量小（无盘口价差）→ 跳过
active_buy_ratio = 主动买量 / 总成交量
```

- QMT tick 免费可得：`lastPrice`/`askPrice1`/`bidPrice1`/`volume`（`xtdata.py` 文档确认）。
- Level2 权威替代：`get_l2_transaction`（`entrustDirection`/`buyNo`/`sellNo`），将来开通 Level2 只需替换 `_active_buy_ratio()` 内部实现。

### 4.5 数据源清单与实时性边界（重要）

| 数据 | 轨道 A 来源 | 轨道 B 来源 | 实时性 | 预置 or 现算 |
|------|------------|------------|--------|-------------|
| 05:00 模型分 score | pipeline | fullpool.json `score_0500` | 隔夜静态 | **预置**（本就静态，无滞后） |
| 主力 5 日净流入 | 东财 fund_flow_history.json | fullpool.json（服务器预置） | 历史累计 | **预置**（⚠️ 8/14 `recommendations` 基本完整，但导出需校验 None） |
| 板块强弱/竞价信号 | 服务器板块聚合 | QMT 本地全板块成分股聚合 | 当日实时 | **QMT 现算**（范围扩大，见 §6-5） |
| 竞价 gap | 腾讯行情 | QMT tick | 实时 | **QMT 现算** |
| 竞价量/量比 | 腾讯行情 | QMT tick/历史日线 | 实时 | **QMT 现算** |
| 换手率 | 腾讯 turnover | QMT vol/FloatVolume | 实时 | **QMT 现算** |
| 主动买占比 | 腾讯 active_buy_ratio | QMT tick 近似 | 实时 | **QMT 现算**（⚠️ 仅连续竞价段有效，09:30 前不用） |
| 5 档盘口 | 腾讯 5 档 | QMT tick 5 档 | 实时 | **QMT 现算** |

**score 口径（定稿）**：`score_0500 = icir_raw_score → score_raw → ml_score`（逐级 fallback，None 处理）。不用 `score`（09:35 资金流重排后的混合分），不用 `pre_market_adjusted_score`（QMT 独立重算）。

**实时性边界结论**：
- 预置的是"本来就静态/历史"的数据（模型分、5日资金流），不存在滞后导致的决策偏差。
- 需要实时的决策数据（竞价、资金、盘口）全部在 QMT 端现算。
- 板块聚合对象 = **候选池所属板块的全部成分股**（比轨道 A 的 Top100 候选聚合更广，规避小样本失真）。

### 4.6 下单与卖出

- 下单：复用 `passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares, "auction_b", 1, "", C)`，quickTrade=1。
- 仓位：`int(total_asset × 0.15 / fill / 100) × 100`，封顶可用现金。
- 卖出：**直接复用 v2.12 卖出逻辑**（T+1 保护、止盈止损、T+2 强平、动态分批）。
- 隔离：`ACCOUNT_TAG="b"` → `C:/alphapilot/b_*_fullchain.json`、`b_ledger_daily.json`、`b_order_locks.json`。

---

## 5. 待办任务清单

| # | 任务 | 内容 | 状态 |
|---|------|------|------|
| 1 | **确认服务器 cron 基线** | 已确认：`crontab` 中 09:25 跑 `pre_market_gate.py`，09:35 跑 `live_momentum_scanner.py` + `MORNING_RANK_MODE=model` → **简报时序基线正确**（model 模式生效） | ✅ 完成 |
| 2 | **服务器 fullpool 导出** | `export_qmt_scores.py` 追加 `{date}.fullpool.json`（全量候选，不碰现有导出） | ⏳ 待做 |
| 3 | **QMT 轨道 B 策略** | 写 `qmt_auction_select_v1.py`（§4.3 完整逻辑） | ⏳ 待做 |
| 4 | **部署指引** | 第二个模拟账户 + nginx 配置 + cron 调度 | ⏳ 待做 |
| 5 | **交叉验证** | DeepSeek Harness 对照 §6 逐条验证 | ✅ 完成（2026-08-16） |

### 5.1 交叉验证结论（已核实采纳）

**4 处实质发现（已逐项人工复核）**：

| # | Harness 发现 | 复核结论 |
|---|-------------|---------|
| 1 | **BOOK_RERANK 默认开**（简报说"默认关"是错的） | ✅ **确认属实**：`morning_live_fund_select.py:44-48` 默认 `"1"`，强度 0.10 |
| 2 | **服务器 cron 状态不明**（两份冲突安装脚本） | ✅ **已用 `crontab -l` + 两份脚本逐一核对**：当前生效 = **`install_opening_scheme_cron.py`**（09:25:55 `pre_market_gate` + 09:35 `MORNING_RANK_MODE=model`）。`install_momentum_scanner_cron.py`（移除 pre_market_gate、RANK_MODE=fund）与 crontab 实况不符，**未生效**。简报基线（model + pre_market 门控）正确 |
| 3 | **轨道 B 需要字段已存在**（`main_net_5d`/`icir_raw_score`/`pre_market_*`） | ⚠️ **部分属实但更微妙**：`daily_recommend.json` 的 `recommendations` 含这些字段，但 `icir_raw_score` 有 **8/44 None**（未参与竞价门控的股票），`full_candidate_pool` 的 `main_net_5d` **83/83 全 None**、`score_raw` 77/83 None → **fullpool 导出必须处理 None，不能直接取字段** |
| 4 | **09:36 服务器 paper_trading 在跑** | ✅ **确认属实**：`paper_trading_signals.py`+`trade_executor.py` 读写 `data/paper_trading.json`，**纯服务器端纸面模拟，不连 QMT 不重复下单**，但与轨道 B 需明确区分 |

**7 个问题结论**：

| 问题 | 结论 | 采纳后的设计调整 |
|---|---|---|
| 1 全量门控性能 | 1 分钟粒度可行，tick 粒度不可行 | QMT 策略改为 **1 分钟 handlebar + 每 5 分钟批量拉取**，tick 只用于持仓监控 |
| 2 tick 近似精度 | 竞价时段失真 | **09:30 前不用主动买占比门**；09:30 后连续竞价才启用 tick 近似 |
| 3 P1 时间窗 | 需补迟到数据截止 | 加 `CALL_DATA_CUTOFF=09:30`，09:30 后到的新数据只更新 gap，不进决策 |
| 4 fullpool 时机 | **建议 06:30 导出纯 05:00 池** | 新增 cron `06:30 export --fullpool`（读 05:00 `daily_recommend.json` 的 `recommendations`） |
| 5 板块聚合范围 | 应扩大到全板块成分股 | `pre_market_gate.py` 的聚合只覆盖 Top100 候选（8/14 有 n=1 板块），轨道 B 用 QMT 本地板块成分股聚合 |
| 6 pre_market 字段 | 不带，QMT 独立重算 | fullpool 只含静态字段，竞价相关全部 QMT 现算 |
| 7 score 口径 | **用 `icir_raw_score`** | 但需 **fallback 链**：`icir_raw_score` → `score_raw` → `ml_score`（None 时逐级回退） |

---

## 6. 待交叉验证的问题清单（重点）

请 DeepSeek Harness 对以下 7 个问题逐条给出结论，并指出任何逻辑矛盾、遗漏或歧义：

1. **全量门控的可行性**：对 fullpool 全部候选（80-500 只）做 tick 拉取 + 门控，QMT 每分钟 handlebar 的性能是否足够？（每 tick 对 500 只拉分笔、算 gap、算主动买）
2. **tick 近似主动买的精度**：无 Level2 时，用"成交价 vs 卖一/买一"判断主动买，与轨道 A 腾讯 `active_buy_ratio`（同花顺口径）的误差是否会改变 Top2 结论？
3. **P1 竞价门控时间窗**：轨道 A 的 pre_market_gate 在 09:25 跑一次（用竞价快照）。轨道 B 在 QMT 里是 09:25-09:30 持续计算，若某候选 09:25 无竞价数据但 09:28 出现，处理策略？
4. **fullpool 导出时机**：若 09:36 导出（在 09:35 scanner 之后），`full_candidate_pool` 已含资金流字段（83 只）。若要在 09:35 前导出纯 05:00 池（135 只），需 06:30 新增 cron。**哪种更符合"轨道 B 让 QMT 独立选股"的意图？**
5. **板块聚合范围**：轨道 B 的板块强弱只对候选池聚合（与轨道 A 一致），是否应扩大到候选池所属板块的所有成分股？（轨道 A 只对 Top100 候选聚合，样本少可能失真）
6. **pre_market_* 字段**：fullpool 导出时若已过 09:25，是否应带上 pre_market 门控结果？还是让 QMT 完全独立重算？
7. **与轨道 A 的评分字段一致性**：fullpool 的 score 用 05:00 原始分（`icir_raw_score`）还是 09:25 调整后的 `pre_market_adjusted_score`？

---

## 7. 关键代码出处与文件清单

### 7.1 服务器端

| 逻辑 | 文件 | 行号 |
|------|------|------|
| 全门控 500 池 | `alphapilot_pipeline_v3.py` | L594 `FULL_POOL_SIZE=500` |
| 竞价门控 Top100 | `pre_market_gate.py` | L42 `CALL_AUCTION_TOP_N=100`, L249 |
| gap 阈值 | `pre_market_gate.py` | L43-51（GAP_LIMIT_UP=9.0 在 L45） |
| 板块聚合 | `pre_market_gate.py` | L164 `aggregate_sector_signals`, L190 `enforce_sector_diversity` |
| 门控规则 1-5 | `pre_market_gate.py` | L338-402 |
| 资金门参数 | `money_flow_gate.py` | L15-19 |
| 资金门判定 | `money_flow_gate.py` | L74-79 |
| 主力5日硬门 | `money_flow_gate.py` | L85-100 |
| 生产资金门调用 | `morning_live_fund_select.py` | L456（hard_main_net_5d=True） |
| 排序选 Top2 | `morning_live_fund_select.py` | L268-292 `select_top_by_score`, L32 `LIVE_TOP_N=2` |
| 全链管线 | `alphapilot_pipeline_v3.py` | 主入口 |
| 实时资金流 | `live_fund_flow.py` | 腾讯/东财抓取 |

### 7.2 QMT 端

| 逻辑 | 文件 | 行号 |
|------|------|------|
| QMT P2 确认 | `qmt_model_full_chain_v2.py` | L894-972 |
| QMT 下单 | `qmt_model_full_chain_v2.py` | L1317-1351 |
| QMT 卖出 | `qmt_model_full_chain_v2.py` | L976-1101 |
| QMT 数据字段 | `xtdata.py` | L315-369（5档）, L684-693（full_tick）, L598-607（l2） |
| QMT 模板 | `qmt_model_full_chain_template.py` | 实盘模板版 |

### 7.3 本地项目文档

| 文件 | 内容 |
|------|------|
| `TRACK_B_LOGIC.md` | 轨道 B 精简逻辑（v1.0） |
| `DESIGN_dual_track.md` | 双轨设计文档（含 4.3a 资金指标来源决策） |
| `BASELINE_qmt_fullchain.md` | QMT 全链策略基线（v2.12 审查） |

### 7.4 关键路径

- 服务器工作目录：`/home/ubuntu/alphapilot/`
- 服务器输出：`output/qmt_scores/{date}.json`、`{date}.candidates.json`（+ 新增 `{date}.fullpool.json`）
- nginx：`/qmt_scores/`
- QMT 本地：`C:\alphapilot\scores\{date}.json`
- QMT 日志：`D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_*.log`
- QMT 引擎日志：`D:\国金QMT交易端模拟\userdata\log\XtClient_Message_*.log`

---

## 8. 给 DeepSeek Harness 的验证要求

请在回答中明确以下格式：

1. **结论**：每个问题（§6 的 7 项）给出明确结论（可行/不可行/需修改）。
2. **逻辑一致性**：轨道 B（§4）是否与轨道 A（§3）逐字段对齐？指出所有不一致处。
3. **数据真实性**：§4.5 的数据源是否在 QMT 免费权限内真实可得？有没有虚构/不可得的字段？
4. **遗漏与歧义**：方案中缺少什么关键细节？哪些表述会让人误解？
5. **风险评估**：轨道 B 上线后最可能失败的 3 个点，以及缓解建议。
