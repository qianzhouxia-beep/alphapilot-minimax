# 轨道 A vs 轨道 B：全链选股策略对比（2026-08-17）

> 目的：一次说清两条轨道从「选股 → 买入」的完整链路差异与各自策略明细，
> 以及**哪些环节共用、哪些环节独立**。
>
> 基线版本：
> - 轨道 A QMT 模拟盘 `track_a/TrackA_track_a_qmt_full_chain_sim.py` **v2.13**
> - 轨道 B QMT 模拟盘 `track_b/TrackB_track_b_qmt_auction_sim.py` **v1.1（fullpool_live 实时池 + 分段买入窗口）**
> - 轨道 B QMT 实盘模板 `track_b/TrackB_track_b_qmt_auction_live.py` **v1.2-tpl**、TDX 模拟盘
>   `track_b/TrackB_track_b_tdx_auction_sim.py` **v1.2**（2026-08-17 起与 QMT 模拟盘 fullpool_live 逻辑一致）
>
> 服务器选股：`live_momentum_scanner.py` + `morning_live_fund_select.py` + `money_flow_gate.py`
> （部署在 `/home/ubuntu/alphapilot/`，供双轨共用）。

---

## 0. 一句话结论

- **轨道 A =「服务器精筛 Top10 → QMT 盘中 P2 动态确认买入」**：选股主体在服务器（06:30 出全池、09:35 重排 Top10），QMT 只做「盘中确认 + 下单」。
- **轨道 B =「服务器 09:36 实时重排全池 → QMT 用服务器全因子门控 + 盘中动态确认买入」**：选股主体同样是服务器（05:00 管线 106 维因子 + 09:35 实时资金重排 + 资金/研报门），QMT 用服务器给的 `money_flow_pass / research_tier / score` 做排序与门控，再叠加自己的 P2 动态确认。
- **两者核心差异在「候选池的范围」与「门控在谁那边算」**；卖出逻辑、仓位、风控**完全共用**。

---

## 1. 全链路时间线对比

| 时点 | 服务器（双轨共用） | 轨道 A（QMT） | 轨道 B（QMT） |
|------|-------------------|---------------|---------------|
| 05:00 | 全市场 106 维因子评分（VM2.5 模型 + ICIR）→ `daily_recommend.json` ~500 只 | — | — |
| 06:30 | `export_qmt_scores.py --fullpool` → `{date}.fullpool.json`（05:00 静态全池） | — | 读 fullpool 兜底（09:36 前） |
| 09:25 | `pre_market_gate.py` 竞价门控（写回 daily_recommend） | — | **P1 竞价门**（09:25-09:30，QMT 本地算 gap/板块强弱，独立重算） |
| 09:30 | — | — | **P2 资金门**（09:30-09:35，QMT 本地算 abr/换手/量比/跌幅） |
| 09:35 | `live_momentum_scanner` 全市场资金流重排：`score = 0.6×管线分 + 0.4×实时资金动量z` → Top50；`morning_live_fund_select` 资金门 + 研报门 → Top2 正式推荐 | — | — |
| 09:36 | `export_qmt_scores.py --fullpool-live` → `{date}.fullpool_live.json`（全因子 + 全部门控后的实时全池） | 拉 `{date}.json`（全评分）+ `{date}.candidates.json`（**Top10 候选**） | **切到 fullpool_live 实时池**（本地优先，远程 nginx 兜底） |
| 09:36-14:57 | — | **P2 动态确认**（价>P935 & 价>VWAP + 5m 放量 + 不追高 + 换手上限 + ABR 门），**按 rank 顺序先到先得**，最多买 2 只 | **P2 动态确认**（同左），按服务器 score/money_pass 顺序遍历，最多买 2 只 |
| 盘中 | — | 卖出逻辑（自适应止损/移动止盈/T+2/Wyckoff/VWAP 早退） | **同一套**卖出逻辑 |

**关键区别**：
1. **候选池范围**：A 用 Top10；B 用整个实时池（08-14 为 44~83 只）。
2. **09:36 前的选股责任**：A 完全等服务器；B 有独立的 P1/P2 竞价门兜底（09:36 前用 05:00 fullpool 自己算），09:36 后切服务器实时池。
3. **买入时序**：A 从 09:36 一直观察到 14:57（全天候窗口）；B 分段窗口 **上午 09:36-11:30 + 午后 13:00-14:00**（14:00 后关闭，尾盘触发 T+1 最差）。B 在每个 bar 持续尝试，直到当日买满 2 只。

---

## 2. 选股策略明细

### 2.1 轨道 A：服务器 Top10 + QMT P2 动态确认

**数据源**：`{date}.candidates.json`（服务器 `export_qmt_scores.py` 09:36 导出，Top10）。
顺序 = 09:35 `morning_live_fund_select` 重排后的**资金门通过者优先、score 降序**。

**QMT 端买入门槛**（`_check_buy`，按 rank 逐只尝试，先到先得）：

| 门槛 | 参数 | 说明 |
|------|------|------|
| 持仓上限 | `MAX_HOLDINGS=4` | 满仓不再尝试 |
| 日买入上限 | `MAX_DAILY_BUY=2` | 每交易日最多 2 笔 |
| 板块权限 | `ALLOW_STAR/CHINEXT/BSE` | 无权限板块跳过该 rank |
| 涨停板 | `_is_limit_up` | 一字/涨停不追，当日跳过该 rank |
| Wyckoff 出货 | `_wyckoff_distribution` | T-1 日线显示 buy-climax / upthrust → 跳过 |
| 换手上限 | `CONF_MAX_TURNOVER=5.0%` | 当日换手 >5% 放弃（回测支撑） |
| ABR 门 | `MIN_ACTIVE_BUY=0.52`（软门） | 09:30 后 P2 触发时主动买占比 ≥0.52；数据缺失不拦截 |
| **P2 动态确认** | 价>P935 & 价>VWAP & 5m 放量 & 不追高 | 核心买入触发（见 2.3） |

**仓位**：单只 `POSITION_PCT=0.15`（总资产 15%）。

### 2.2 轨道 B：服务器实时全池 + 服务器门控 + QMT P2 动态确认

**数据源**（09:36 后）：`{date}.fullpool_live.json`，行字段 = `score`（09:35 融合分）、
`money_flow_pass`（服务器资金门）、`research_tier`（研报门）、`live_momentum_z`、
`main_net`、`main_net_5d`、`active_buy_ratio`、`turnover`、`volume_ratio`、
`change_pct`、`pre_market_gap_pct`、`pre_market_action`。

**QMT 端买入门槛**（`_check_buy`，live 模式下按 `money_pass` 优先 + `score` 降序遍历）：

| 门槛 | 来源 | 说明 |
|------|------|------|
| 持仓上限 / 日买入上限 | QMT | 同 A（4 / 2） |
| **服务器资金门** | `money_flow_pass` | **直接采信服务器结果**（106 维因子 + 资金门已在服务器算好） |
| **服务器研报门** | `research_tier` | prefer/s1/s2 优先（排序参考） |
| 板块权限 / 涨停 / Wyckoff | QMT | 同 A |
| ABR 软复检 | QMT | 仅软检查，不否决（服务器已覆盖） |
| **P2 动态确认** | QMT | 同 A（见 2.3） |

**09:36 前兜底**（`fullpool_live` 缺失或未到点）：用 05:00 `fullpool.json`，QMT 本地跑
**P1 竞价门**（gap≥9% 近涨停剔、gap<-2% 剔、gap<0 且板块弱剔、gap<-0.5% 降权、gap≥2% 加分、
板块分散 Top10≤2/Top20≤3/池≤5）+ **P2 资金门**（abr≥0.52、换手 2~35%、量比≥0.8、
跌幅≥-5%、主力5日净流入≥0）。

### 2.3 共用：P2 动态确认（`_p2_decide`，双轨相同）

```
窗口        09:35 ~ 14:57（A）；B 分段：09:36-11:30 + 13:00-14:00，14:00 后关闭
趋势        收盘价 > P935(09:35 首根5m收盘) 且 收盘价 > 盘中 VWAP
量能        最近 2 根 5m bar 至少 1 根 vol > MA5(vol)×1.3 且收阳
不追高      收盘价 <= 昨收 × 1.08
换手        若可算且 >5% → 放弃（A 还有 ABR 软门 ≥0.52）
触发价      返回触发那根 5m 的收盘价作为委托价
```

### 2.4 服务器端选股明细（双轨共用，B 的实时池即其结果）

**05:00 管线**（`alphapilot_pipeline_v3.py`，106 维因子评分）：
`recommend.py` 用 VM2.5（XGBoost 三模型）+ ICIR 权重 → 启动池∪主线旁路池内评分 →
业绩门（预减/首亏/续亏剔除）→ 资金门（arm A 硬门 / arm B 软加权）→ 万得板块 prefer/avoid →
大盘环境门（crash+rotation_dead 空仓）→ 板块资金轮动门 → K 位置门 → 跟庄书 C 档（MA30 向下剔、
高位大阴线>6%剔）→ 操盘接力/趋势/热点软加分 → LLM 审核 ± → 输出 ~500 只。

**09:35 实时重排**（`live_momentum_scanner.py`）：
```
score = pipeline_z × 0.6 + 实时资金动量z × 0.4
实时动量z = 全市场横截面 z-score（主力净额 0.35 / 主动买比 0.25 / 涨跌幅 0.25 / 换手 0.15）
门控      = 排除列表 + 近涨停过滤（涨幅≥涨停价97% 剔）+ 板块分散（Top10 同板块≤2、全池≤4）
输出      = Top50 recommendations + 全池 full_candidate_pool
```

**09:35 资金门 + 研报门**（`morning_live_fund_select.py` → `money_flow_gate.py`）：
```
资金硬门   abr≥0.52 且 换手 2~35% 且 量比≥0.8 且 当日跌幅≥-5%
           + 主力5日：3日&5日全负且近5日零流入 → 硬淘；5日<-1亿 → 硬淘
研报门     soft_hybrid：avoid 软降权、prefer 加分、竞价/资金主线硬加权
排序       money_flow_pass 优先，score 降序（可选书价分位 ±5% 微调）
```

---

## 3. 共用 / 独立一览

| 环节 | 轨道 A | 轨道 B | 是否共用 |
|------|--------|--------|----------|
| 05:00 因子评分（106 维） | 服务器 | 服务器 | ✅ 共用 |
| 09:35 实时资金重排 | 服务器 | 服务器 | ✅ 共用 |
| 09:35 资金门 / 研报门 | 服务器 | 服务器 | ✅ 共用（B 直接采信结果） |
| 09:25-09:30 竞价门（P1） | 服务器 pre_market | QMT 本地（09:36 前兜底） | ❌ 独立 |
| 09:30-09:35 资金门（P2） | — | QMT 本地（09:36 前兜底） | ❌ 独立 |
| 候选池范围 | Top10 | 实时全池 44~83 只 | ❌ 不同 |
| P2 动态确认（盘中触发） | QMT | QMT | ✅ 同一套 `_p2_decide` |
| ABR 门 | QMT 软门 ≥0.52 | QMT 软复检 | ⚠️ 阈值相同、B 不强否决 |
| Wyckoff 出货门 | QMT | QMT | ✅ 共用 |
| 卖出逻辑（止损/止盈/T+2/早退） | QMT | QMT | ✅ **完全相同** |
| 仓位（15%）/ 持仓上限（4）/ 日买上限（2） | QMT | QMT | ✅ 共用 |
| 交易文件隔离 | `sim_trades_fullchain.json` | `b_trades_fullchain.json` | ❌ 独立前缀 `b_` |

---

## 4. 核心差异小结（为什么两条轨道不同）

1. **选股范围与决策时点**
   - A：服务器 Top10，09:36~14:57 全天候观察买入。
   - B：服务器实时全池，分段窗口买入——上午 09:36-11:30 + 午后 13:00-14:00，
     （2026-08-17 放宽，v1.1；原 09:40 截止在 P2 触发分布下捕获率 0%）。

2. **B 的 09:36 后不再「只看资金/量比」**
   - 升级前（v1.0 早期）：B 只消费 05:00 静态 `score_0500` + QMT 本地资金四门，
     相当于把「106 维因子评分」丢掉，只剩资金面。
   - 升级后（2026-08-17）：B 消费 `fullpool_live`，服务器已把 **106 维因子 +
     实时资金动量 + 资金门 + 研报门**全部算好打进 score/money_flow_pass/research_tier，
     QMT 直接采信——**与轨道 A 用的是同一套服务器选股能力**。

3. **回测对照（2026-08-03 ~ 08-14，T+1）**

| 口径 | n | 胜率 | 均值 T+1 | 累计 T+1 |
|------|---|------|---------|---------|
| 05:00 静态池（旧 B） | 14 | 85.7% | +2.68% | +37.52% |
| 09:35 实时池（新 B） | 15 | 86.7% | **+4.28%** | **+64.12%** |

> 样本偏小（9 天），方向性结论：实时池叠加当日资金动量后累计收益约为静态池 1.7 倍。

---

## 5. 文件对照

| 角色 | 轨道 A | 轨道 B |
|------|--------|--------|
| QMT 模拟盘 | `track_a/TrackA_track_a_qmt_full_chain_sim.py` | `track_b/TrackB_track_b_qmt_auction_sim.py` |
| QMT 实盘模板 | `track_a/TrackA_track_a_qmt_full_chain_live.py` | `track_b/TrackB_track_b_qmt_auction_live.py` |
| TDX 模拟盘 | `track_a/TrackA_track_a_tdx_full_chain_sim.py` | `track_b/TrackB_track_b_tdx_auction_sim.py` |
| 免费逐笔数据 | —（A 直接读 mootdx_feed） | `track_b/mootdx_feed.py`（B 部署为独立进程，A 也读） |
| 服务器导出 | `server/export_qmt_scores.py`（默认 `{date}.json`） | `server/export_qmt_scores.py --fullpool-live` |
| 独立服务 | — | `track_b/mootdx_feed.py`（交易日 09:15-15:00 常驻） |

---

## 6. 补充：B 的 live 池读取实现要点

- 触发时点：`LIVE_FULLPOOL_MIN = 09:36`，`USE_SERVER_GATES = True`。
- 加载：`_load_fullpool` 分 live/classic 双路径——09:36 后优先 `{date}.fullpool_live.json`
  （本地 → 远程 nginx `http://150.158.100.236/qmt_scores/` 兜底），失败回退 05:00 fullpool。
- 决策窗口：live 模式下 `eff_decide = 09:36`；买入窗口分段
  `BUY_AM_END_MIN=11:30` + `BUY_PM_START_MIN=13:00 / BUY_PM_END_MIN=14:00`。
- 门控：`_p2_gate` live 分支直接采信 `money_flow_pass` / `research_tier` / `score`；
  classic 分支保留 QMT 本地四门（abr/换手/量比/跌幅 + 主力5日）。
- 混合安全：若 live 池行与经典池行混用，`_p2_gate` 按 `is_live_row` 判别各自走对应分支。
