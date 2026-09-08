# 交易策略档案

> 状态：**生产生效**（除非标注"提案/待讨论"） ｜ 最后更新：2026-09-03
>
> 本文只讲 **买卖模型**（QMT/通达信何时买、何时卖）。候选名单从哪来、怎么排序，见 **选股模型**：[`selection_vs_execution.md`](./selection_vs_execution.md)。

**Track A 基因重排 + rank≤3（2026-09-03，v2.34 / v2.34-tpl，仅 QMT 轨道 A）**：server 导出 `candidates.json` 时对 Top10 做池内重排——`gene = rank(近10日涨停次数)+rank(MA25斜率)+rank(近10日收益)`（T-1），资金**不**参与排序（仍是硬门）。QMT `MAX_CAND_RANK=3`：新序 rank 1–3 可进 P2。网页融合榜 / `{date}.json` 顺序不变。依据：真实 34 日 gene≤3 甜区。inbox `2026-09-03-gene-window-long-revalidate.md`。

**Track A 弱市破位敏感卖出（2026-09-03，v2.33 / v2.33-tpl，仅 QMT 轨道 A）**：server 导出 JSON 新增 `market_env`（全 A 主力净流入 5 日累计全历史分位 → `state5_q`，q=1=深流出弱市）。弱市下**只动止损/持仓，止盈不动**：动态亏损下限 ×0.6（止损更紧）；T+2 14:45 展期需「现价 ≥ 25 日均线」；T+3 持有上限仅「现价 < 25 日均线」（破位）才卖——**趋势完好继续拿，取消硬时间剔除，浮亏但趋势不破也拿**。**止盈侧（peel 冲高回落、trail 移动止盈）与非弱市完全一致**（v2.33 用户明确：止盈维持原样）。破位线 = 25 日均线（截至昨日收盘，用户指定口径；v2.31 当日 VWAP 口径、v2.32 peel 收紧均未部署即被取代）。非弱市行为与 v2.30 完全一致；读不到 market_env 按非弱市。TDX/ptrade/轨道 B 本次未改。inbox `2026-09-03-weak-regime-breakdown-sell.md`。

**Track A `vwap_weak_early`（2026-09-02，v2.30 / v2.30-tpl）**：昨 14:45 跌破日 VWAP 后，次日 09:35-09:50 **第一次仍低于昨 VWAP 只记确认不卖**；下一分钟仍低于才卖。涨回昨 VWAP 撤销。不是 `t2_force`。轨道 B 同步（v2.7 / v1.18）。inbox `2026-09-02-xiannong-vwap-weak-early-sold-low.md`。

**Track A rank 门槛（2026-09-01，v2.29 / v2.29-tpl）**：只让 09:35 `{date}.candidates.json` 的 **rank 1-2** 进入 P2。服务器仍导出 Top10；rank 3+ 当日不买。**P2 本身未改**。两只都不过 P2 → 当天空仓。`MAX_DAILY_BUY` 仍=2。**不要和网页融合 Top10 混。** inbox `2026-09-01-rank-le2-p2-gate.md`。

**Track A 换仓（2026-09-01，v2.29）**：`ROTATION_ENABLE=False`。满仓不再踢最弱一只腾位；等正常卖出腾位。不是 T+1 强制清仓（T+0/T+1 本来就免疫 rotation）。轨道 B 仍开着 rotation。

**P2 趋势（2026-08-26）**：用滚动 **session low**（`c > day_low`）判断从日内动态最低点抬升，替代 `c > P935` + `c >= prev_close` 相对快照。**池子排名、动量确认、放量、no-chase、日高 guard 不变。**

**Track B fallback 买入窗（2026-08-26，v2.2）**：`money_flow_pass=True` 无 rank 限制。fallback：**10:00 前 rank≤10**；**10:00 后 rank≤15**（前 10 名晚 P2 仍可买）；**rank>15 或 fund_hard_fail → 不买**（宁可空仓）。ST/*ST 仍全链路硬过滤。

**P2 no-chase（2026-08-26）**：分板块 — 主板 +6%、科创/创业板 +10%、北交所 +12%；日高位置 ≤85%。Track A/B 全客户端同步。

**P2 换手门（2026-08-29 复核）**：换手率 >5% 跳过（`CONF_MAX_TURNOVER=5.0`）。04~08 回测 393 触发确认：换手越低 T+1 越好单调（<1% +5.79%/胜率92.7% → 4~5% +0.48% → 5~6% -0.78% → >10% -1.96%）。**不设下界**——低换手是"潜伏未启动"特征，P2 池内换手太小不影响收益（与直觉相反）。详见 inbox `2026-08-29-turnover-range-and-no-chase.md`。

## 买入规则

### Track A 生产策略（QMT/TDX 全链 v2.29，`production_strategies/track_a/`）

| 项 | 规则 |
|---|---|
| 选股 | 服务器 `{date}.candidates.json` **只允许 rank 1-2 进 P2**（Top10 仍导出，买卖端过滤） |
| 买点 | P2 动态确认（**c>session_low** 且>VWAP / 5m量比>1.3 / **分板块 no-chase** / **日高≤85%** / 换手≤5%）；**fund_hard_fail → skip** |
| **ABR 门（v2.13 新增）** | P2 触发后连续竞价时段（≥09:30）检查主动买占比，**<0.52 → 当日放弃**（`skip_low_abr`）。QMT 优先读 mootdx_feed 当日累计逐笔 ABR（口径=回测 P2_cum），回退 QMT L1 逐笔近似；TDX 用盘口买一档量占比近似。**软门**：ABR 不可用不拦截 |
| 执行 | 09:35~14:57 观察窗，**仅 Top2 内**先到先得，日限 2 笔、持仓 4 只、每笔 15% 总资产；两只都不过 P2 则不买 |
| 数据 | `C:\alphapilot\l2_feed\{date}.json`（需先启动 `mootdx_feed.py` 独立进程） |

> **ABR 门依据（2026-08-16 扩样本复验，114候选/20日真实Top10）**：累计 ABR≥0.52
> 使 T+1 胜率 42.3%→54.2%、T+1 均收益 -0.46%→+0.36%。ABR<0.50 是强负信号
> （T+1 均 -1.54%、胜率 31%）。**卖出侧不生效**（ASR 早退负优化，弱市主动卖高是
> 洗盘）——卖出继续依赖 Wyckoff BC / T+2 / peel / VWAP 弱势早退。
> 完整报告：`production_strategies/track_a/BT_ABR_GATE_REPORT.md`

### 当前生效（服务器管线，`morning_live_fund_select.py` + `trade_executor.py`）

| 项 | 规则 |
|---|---|
| 选股 | 09:35 终选 Top2（`morning_live_picks.json`） |
| 买点 | 盘中 VWAP 回踩 5 分钟线低位（用户指定，2026-08-04 定） |
| 执行 | 09:42/09:52 轮询 + 日内低频轮询（cron `executor_low`） |
| 展示 | 前端显示实际成交价 |

### ⚠️ 回测提醒（`docs/盘中买卖点回测结论_2026-08-06.md`）

- VWAP 回踩在回测中**跑输"09:35 直接买"基线**：触发少（13/110）且胜率低（30.8%）。强势票很少回踩到 VWAP 下方 0.8%，能回踩到这么深的往往是当天偏弱票。
- 09:35 直接买基线：30min +0.50%、胜率 53.6%，**比所有买卖点形态都好**。
- `low_open_recover`（低开收回）30min 胜率 66.7% 是唯一亮点，但 60min 转负，像短脉冲。
- **结论：选股比买卖点重要。买卖点只优化 ±5% 内的边际。**

### 候选（待讨论，未上线）
- `low_open_recover` 优先：09:40 前若低开>1%且已收回昨收上方 → 实时价成交（胜率 66.7% vs 直接买 53.6%）

## 卖出规则

### 当前生效
| 项 | 规则 |
|---|---|
| 止盈 | T+2 收盘卖（可交易协议，`trade_executor.py` Plan C） |
| 止损 | 峰值回撤（`trail_pct`）机制，默认回撤 6% |

### ⚠️ 回测提醒
- **回撤 6% 卖是最差的卖法**：触发后股票平均反弹 +0.50%，delta=-5.58%，卖在坑底。
- `vol_stall`（放量滞涨）是唯一正贡献卖出信号（delta=+4.30%），但 **WorkBuddy 交叉验证发现它依赖 vol_ma"含当前 bar"的实现巧合，改用"前5根均量"后 Δ 归零** → **暂不实施**。
- `adaptive_exit.py`（自适应止损）：减少误止损 56%（25→11 次），收益增益仅 +0.03%，可作为风控增强启用（低风险）。

## 出场规则（adaptive_exit.py）

| 档位 | 固定止损 | 自适应 |
|---|---|---|
| 高波动(>45%) | 25 次 | 11 次（-56%） |
| 收益影响 | — | Δ+0.03%（统计不显著） |

结论：保留自适应止损作为风控，收益端别指望它。

## 仓位规则（`market_env_gate.py` + `permission_gate.py`）

| position_exposure | 条件 | 推荐池 | TopN |
|---|---|---|---|
| 0.0 | crash_day 且 rotation_dead | 0 | nuclear |
| 0.25 | 许可OFF非nuclear；或许可ON+severe(up3<200) | Top10 | Top1 |
| 0.5 | 许可ON+weak/tech；或severe且up3≥200 | Top50 | Top2 |
| 1.0 | 许可ON且指数非弱 | Top50 | Top2 |

## 待验证/数据缺口

| 项 | 状态 |
|---|---|
| 资金背离卖出信号 | 需 `institutional_watch_history.jsonl` 积累 20+ 交易日（约 09 月初） |
| 资金强度买点 | 同上 |
| vol_ma 定义统一 | ✅ 已统一：`rolling(5).mean().shift(1)` 前5根均量（2026-08-15 全量统一，含当前 bar 变体已废弃） |

## 相关文档
- `docs/盘中买卖点回测结论_2026-08-06.md` — 第一轮回测
- `docs/WB_交叉验证报告_盘中买卖点_2026-08-06.md` — WB 独立复核
- `docs/给WorkBuddy的同步稿_盘中买卖点_2026-08-06.md` — 三方同步稿
- `docs/TRADABLE_V3_PLAYBOOK.md` — 可交易协议
