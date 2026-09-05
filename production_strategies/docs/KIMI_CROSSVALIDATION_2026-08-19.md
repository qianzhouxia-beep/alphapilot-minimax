# AlphaPilot 全链选股策略 · 交叉验证委托文档（发给 Kimi）

> 作者：AlphaPilot 主控 Agent
> 日期：2026-08-19
> 读者：**Kimi**（全新 Agent，无本项目任何上下文）
> 用途：本文档是**自包含交叉验证委托**——从系统背景、整套选股逻辑、到本次 3 处代码修改、真实 bug 案例、待验证问题，全部在此。读完本文即可独立审查，无需访问服务器、QMT 或历史对话。
>
> **验证任务**：逐条核对本次 3 处修改（动态 T+2 强平线 / 买入端滑点保护 / VWAP 数据源）的数学正确性、边界情况、数据源稳定性，以及是否与整套选股/卖出逻辑自洽。

---

## 目录

1. [系统背景](#1-系统背景)
2. [整套选股逻辑全貌（Track A / Track B 双轨）](#2-整套选股逻辑全貌track-a--track-b-双轨)
3. [本次修改的三个问题（真实 bug）](#3-本次修改的三个问题真实-bug)
4. [修改 1：动态 T+2 强平线](#4-修改-1动态-t2-强平线)
5. [修改 2：买入端滑点保护](#5-修改-2买入端滑点保护)
6. [修改 3：VWAP 数据源（QMT 原生优先）](#6-修改-3vwap-数据源qmt-原生优先)
7. [真实数据验证（300591 08-19）](#7-真实数据验证300591-08-19)
8. [请 Kimi 重点核查的问题](#8-请-kimi-重点核查的问题)
9. [版本与文件清单](#9-版本与文件清单)

---

## 1. 系统背景

一套**A 股量化选股 + 自动交易**系统，分两大部分：

1. **服务器端**（Linux，24/7）：
   - 每天 05:00 跑全市场选股管线（106 维因子 + 门控 + ML 打分 + LLM 审计），产出候选池。
   - 09:25-09:35 盘中阶段做集合竞价门控、实时资金流重排、资金门/研报门，选 Top2。
   - 把结果导出成 JSON 文件（`{date}.json` / `{date}.candidates.json` / `{date}.fullpool.json` / `{date}.fullpool_live.json`），通过 nginx 静态托管。
2. **本地交易端**（Windows）：
   - **QMT**（国金量化终端，Python 策略，模拟/实盘双账户）。
   - **TDX**（通达信 TdxQuant，Python 策略，模拟盘，帮朋友跑）。

**双轨并行**：
- **Track A**：服务器精筛 Top10 → QMT/TDX 盘中 P2 动态确认买入。
- **Track B**：服务器 09:36 实时重排全池 → QMT/TDX 用服务器全因子门控 + 盘中动态确认买入。

Track A 和 Track B 分别在**独立模拟账户**上运行，用于比较与保底；卖出逻辑、仓位、风控两者**完全共用**。

---

## 2. 整套选股逻辑全貌（Track A / Track B 双轨）

### 2.1 全链路时间线

| 时点 | 服务器（双轨共用） | Track A（QMT/TDX） | Track B（QMT/TDX） |
|------|-------------------|---------------------|---------------------|
| 05:00 | 全市场 106 维因子评分（VM2.5 模型 + ICIR）→ `daily_recommend.json` ~500 只 | — | — |
| 06:30 | `export_qmt_scores.py --fullpool` → `{date}.fullpool.json`（05:00 静态全池） | — | 读 fullpool 兜底（09:36 前） |
| 09:25 | `pre_market_gate.py` 竞价门控（写回 daily_recommend） | — | **P1 竞价门**（09:25-09:30，QMT/TDX 本地算 gap/板块强弱） |
| 09:30 | — | — | **P2 资金门**（09:30-09:35，本地算 abr/换手/量比/跌幅） |
| 09:35 | `live_momentum_scanner` 全市场资金流重排 → `morning_live_fund_select` 资金门+研报门 → Top2 正式推荐 | — | — |
| 09:36 | `export_qmt_scores.py --fullpool-live` → `{date}.fullpool_live.json` | 拉 `{date}.json` + `{date}.candidates.json`（Top10） | **切到 fullpool_live 实时池** |
| 09:36-14:57 | — | **P2 动态确认**（价>P935 & 价>VWAP + 5m 放量 + 不追高 + 换手上限 + ABR 门），按 rank 先到先得，最多买 2 只 | **P2 动态确认**（同左），按服务器 score/money_pass 顺序遍历，最多买 2 只 |
| 盘中 | — | 卖出逻辑（自适应止损/移动止盈/T+2/Wyckoff/VWAP 早退） | **同一套**卖出逻辑 |

### 2.2 服务器端选股明细（双轨共用）

**05:00 管线**（106 维因子评分）：
`recommend.py` 用 VM2.5（XGBoost 三模型）+ ICIR 权重 → 启动池∪主线旁路池内评分 → 业绩门（预减/首亏/续亏剔除）→ 资金门 → 万得板块 prefer/avoid → 大盘环境门 → 板块资金轮动门 → K 位置门 → 跟庄书 C 档 → 软加分 → LLM 审核 → 输出 ~500 只。

**09:35 实时重排**：
```
score = pipeline_z × 0.6 + 实时资金动量z × 0.4
实时动量z = 全市场横截面 z-score（主力净额 0.35 / 主动买比 0.25 / 涨跌幅 0.25 / 换手 0.15）
门控     = 排除列表 + 近涨停过滤 + 板块分散（Top10 同板块≤2、全池≤4）
```

**09:35 资金门 + 研报门**：
```
资金硬门   abr≥0.52 且 换手 2~35% 且 量比≥0.8 且 当日跌幅≥-5%
           + 主力5日：3日&5日全负且近5日零流入 → 硬淘；5日<-1亿 → 硬淘
研报门     soft_hybrid：avoid 软降权、prefer 加分、竞价/资金主线硬加权
排序       money_flow_pass 优先，score 降序
```

### 2.3 客户端买入门槛

**P2 动态确认**（`_p2_decide`，双轨/两端相同）：
```
窗口        09:35 ~ 14:57（A）；B 分段：09:36-11:30 + 13:00-14:00，14:00 后关闭
趋势        收盘价 > P935(09:35 首根5m收盘) 且 收盘价 > 盘中 VWAP
量能        最近 2 根 5m bar 至少 1 根 vol > MA5(vol)×1.3 且收阳
不追高      收盘价 <= 昨收 × 1.08
换手        若可算且 >5% → 放弃（A 还有 ABR 软门 ≥0.52）
触发价      返回触发那根 5m 的收盘价作为委托价
```

**买入门槛链**（按 rank 逐只尝试）：持仓上限（4）→ 日买入上限（2）→ 板块权限 → 涨停不追 → Wyckoff 出货门 → P2 动态确认 → 下单。

**仓位**：单只 `POSITION_PCT=0.15`（总资产 15%）。

### 2.4 卖出逻辑（双轨共用，本次修改的重心）

卖出链路按优先级依次判断（QMT/TDX 六文件一致）：

1. **T+1 保护**：当日买入不卖。
2. **跌停保护**：当日跌幅 ≤ 跌停阈值可卖（异常跳水 hold）。
3. **Wyckoff 持仓买入高潮**（09:35-09:50）：T-1 出现 buy-climax → 早退。
4. **VWAP 弱势早退**（09:35-09:50，14:45 确认）：收盘价 < 当日 VWAP → 标记 vwap_broken → 次日早盘卖出。
5. **自适应止损 hard_stop**（≥14:45）：`ret ≤ hs×100` 强平。`hs = DEF_HARD_STOP - dev×0.10`，dev = 年化波动率 - 0.30。
6. **T+2 条件强平 + 动态强平线**（≥14:45）——**本次修改 1**，详见 §4。
7. **动态分批止盈 peel**（盘中）：`ret ≥ ta×100` 后回落 pb 阈值 → 分批卖。

---

## 3. 本次修改的三个问题（真实 bug）

2026-08-19 实盘暴露两个 bug，本次做了 3 处修改：

1. **万里马(300591)**：08-18 P2 触发价 7.88，市价单实际成交 8.54（滑点 +8.4%）。08-19 当日真实跌 -7.02%（收 7.82，昨收 8.41，当日振幅 6.9%），但相对虚高成本 8.54 是 -8.7%，被旧「T+2 固定 0% 强平线」在 14:45 强制卖出。
2. **西点药业(301130)**：盈利 +33% 仍被 `t2_force_after_extend` 强平。根因：QMT 5m K线 volume 单位是「手」(100股)、amount 单位是「元」，旧代码 `amount/volume` 直接把 VWAP 放大 100 倍（算出 806.98，真实股价约 8.07），导致 `price < vw` 恒真 → `vwap_broken` 恒置位 → 盈利票也被提前卖。

**结论**：两个 bug 都源于「计算/单位错误」，不是 QMT 数据抓取错误。

---

## 4. 修改 1：动态 T+2 强平线

### 4.1 代码

```python
# 常量
T2_FORCE_AMP_FRAC = 0.50        # fraction of day amplitude (%) added to the floor
T2_FORCE_AMP_MIN = 4.0          # amplitude below this adds no extra tolerance
T2_FORCE_VOL_K = 0.10           # +0.10 annual vol -> -1pp more tolerance
T2_FORCE_FLOOR_MAX = -0.10      # absolute floor (never below hard_stop)
VOL_BASELINE = 0.30             # 20-day annualized vol baseline

def _day_amplitude_pct(C, code):
    """Today's intraday amplitude in % of prev close (high-low)/prev*100."""
    pc = _get_prev_close(C, code)          # 昨收
    bars = _get_m5_bars(C, code)           # [(tmin, open, close, high, low, vol), ...]
    hi = max(b[3] for b in bars)
    lo = min(b[4] for b in bars)
    return max(0.0, (hi - lo) / pc * 100.0)

def _t2_force_floor(C, code):
    """Dynamic T+2 force-close floor (negative %)."""
    amp = _day_amplitude_pct(C, code)                # 当日振幅% (高-低)/昨收*100
    vol = _annual_vol(C, code) or VOL_BASELINE       # 20日年化波动率 (0.10~0.80)
    if amp > 0:
        tol = max(0.0, amp - T2_FORCE_AMP_MIN) * T2_FORCE_AMP_FRAC / 100.0
    else:
        tol = 0.0
    if vol > VOL_BASELINE:
        tol += (vol - VOL_BASELINE) * T2_FORCE_VOL_K
    floor = -tol
    if floor < T2_FORCE_FLOOR_MAX:
        floor = T2_FORCE_FLOOR_MAX
    return floor
```

### 4.2 卖出分支（≥14:45，hard_stop 判断在前）

```python
if now_min >= T2_FORCE_HHMM:
    if pos.get("t2_extended"):
        # 已延长到期 -> 强平
        _do_sell(C, code, pos, price, "t2_force_after_extend ...")
        continue
    force_floor = _t2_force_floor(C, code) * 100
    if ret < force_floor:
        # 亏损跌破动态强平线 -> 强平
        _do_sell(C, code, pos, price, "t2_force ... floor=...")
        continue
    hold_days = _hold_days(pos, today)
    if (hold_days >= T2_EXTEND_MAX_DAYS          # 3天
            or pos.get("wy_bc_armed")            # Wyckoff 早退信号
            or pos.get("vwap_broken")            # VWAP 早退信号
            or ret <= hs * 100):                 # 硬止损
        _do_sell(C, code, pos, price, "t2_force_after_extend ...")
        continue
    pos["t2_extended"] = True                    # 盈利无早退信号 -> 延长到 T+3
```

### 4.3 设计意图

- 旧逻辑：14:45 `ret < 0`（固定 0%）就强平。
- 新逻辑：强平线随「当日振幅 + 年化波动率」加深（封底 -10%）。宽振幅/高波动票的正常回撤在当日区间内可持有到 T+3。
- `hard_stop`（自适应 hs，默认 -10%，高波动时加深如 -13%）仍**先于**强平线生效，接管真正的尾部风险。

---

## 5. 修改 2：买入端滑点保护

```python
MAX_BUY_SLIP_PCT = 0.02

# P2 触发价确认之后、下单之前：
_live = _get_last(C, code)   # QMT 1m 收盘或 tick lastPrice
if _live and _live > fill * (1 + MAX_BUY_SLIP_PCT):
    # 实时价已比触发价高 2% 以上 -> 不追买，候选留到下一根 bar 重试
    continue
```

**设计意图**：P2 触发价是 5m 收盘价，快涨时市价单成交价远超触发价（300591 08-18：触发 7.88 实际成交 8.54，+8.4%）。虚高成本把次日 -1% 的正常回撤变成 -8.7% 深亏，被旧固定 0% 强平线误杀。现在实时价高于触发价 2% 以上就**不追买**。

---

## 6. 修改 3：VWAP 数据源（QMT 原生优先）

```python
def _day_vwap(C, code):
    """Today's day VWAP (分时均价, CNY/share)."""
    # 主路径：QMT 原生 get_full_tick
    ticks = C.get_full_tick([code])
    t = ticks.get(code)
    amt = float(t.get("amount") or 0)     # 当日累计成交额 (元)
    pv  = float(t.get("pvolume") or 0)    # 当日累计成交量 (股)
    lp  = float(t.get("lastPrice") or 0)  # 最新价
    if amt > 0 and pv > 0 and lp > 0:
        v = amt / pv                      # 权威分时均价，零单位换算
        if 0.5 * lp <= v <= 2.0 * lp:     # 合理性护栏，拒绝单位错配
            return v
    # 兜底：5m K线 amount/(volume*100)（手->股换算）
    ...
```

**设计意图**：QMT `get_full_tick` 的 `amount`(元)/`pvolume`(股) 即 QMT 分时图「均价」黄线，零单位换算、最权威。合理性护栏 `0.5×lastPrice ≤ VWAP ≤ 2×lastPrice` 兜底，任何残留单位错配（如 100x）都会被拒并落回 5m K线兜底路径（`amount/(volume×100)`）。`get_full_tick` 不可用时 `try/except` 自动落回 5m。

---

## 7. 真实数据验证（300591 08-19）

**日线数据**：
- 08-18：开 8.39 收 8.41 高 8.65 低 8.28（振幅 4.61%）
- 08-19：开 8.33 收 7.82 高 8.36 低 7.78（振幅 6.9%，跌 7.02%）

**动态强平线计算**（昨收 8.41，高 8.36 低 7.78，振幅 6.9%，年化波动率 ~0.6）：
```
tol = (6.9 - 4.0) × 0.5 / 100 + (0.6 - 0.3) × 0.1
    = 0.0145 + 0.03 = 0.0445
floor = -4.45%
```

| 场景 | 成本 | 08-19 价 | ret | 判定 |
|------|------|---------|-----|------|
| 无滑点 | 7.88 | 7.80 | **-1.0%** | > floor(-4.45%) → **持有到 T+3** ✓ |
| 有滑点 | 8.54 | 7.80 | **-8.7%** | < floor(-4.45%) → **仍强平** ✓（说明滑点保护必要） |

---

## 8. 请 Kimi 重点核查的问题

### 数学/量纲
1. `_t2_force_floor`：amp 单位是 %，`tol = (amp-4)×0.5/100` 把百分比换算成小数再取负，是否正确？`(6.9-4)×0.5/100 = 0.0145` 对应「每 1% 振幅给 0.5% 容差」，量纲是否自洽？
2. `T2_FORCE_FLOOR_MAX=-0.10` 固定，而 hard_stop 自适应（默认 -0.10，高波动时如 vol=0.6 → hs≈-13%）。「floor(-10%) 浅于 hs(-13%)」时 hard_stop 是否形同虚设？还是说这正是「floor 管正常回撤、hs 管尾部」的意图？（注意 hard_stop 判断在 floor 之前）
3. 用 300591 真实数据：振幅 6.9% 时 floor=-4.45%，但当日真实收跌 -7.02% 且收在近低点。这个 case 里动态 floor 会让「真走弱的票」继续持有到 T+3——这是过度宽容还是合理容错？宽振幅票是否真能避免误杀？

### 滑点保护
4. 滑点保护 2% 阈值：P2 触发是 5m 收盘价，tick 快速跳价超 2% 的强势票会被一直跳过（不追买），会不会漏掉真正该买的机会？与「不追高」规则（收盘价 ≤ 昨收×1.08）的权衡如何？
5. `_get_last` 用的是 1m 收盘或 tick lastPrice，与 P2 触发价 `fill`（5m 收盘）本身就有天然时间差。这个「触发价 vs 实时价」的比较是否会有误触发（比如刚好在 5m 边界）？

### VWAP 数据源
6. `_day_vwap` 主路径 `0.5x~2x` 护栏是否过宽/过窄？集合竞价 09:25-09:35 期间 `get_full_tick` 的 `amount/pvolume` 是否可靠（是否包含竞价成交）？
7. 若 `get_full_tick` 返回的 `amount/pvolume` 在盘中某个时刻与 5m 兜底路径结果偏差较大（比如 2-3%），哪个更可信？

### 卖出逻辑自洽性
8. 持仓跨日边界：T+2 14:45 延长后（`t2_extended=True`），T+3 14:45 直接 `t2_force_after_extend` 强平，逻辑是否自洽？延长期间若 ret 从正转负且跌破动态 floor，会不会漏卖（因为 `t2_extended` 分支直接 continue 强平，不检查 floor）？
9. `vwap_broken` 在 14:45 确认、次日 09:35-09:50 卖出。若 VWAP 数据源切换后（tick 主路径）`vwap_broken` 触发频率变化，是否会影响卖出节奏？
10. 6 个文件同步后，是否还有其它调用 `_day_vwap` / 强平线的地方没覆盖？（请核对：`_check_sell`、`_rotation_sell`、`_p2_decide`）

---

## 9. 版本与文件清单

| 角色 | Track A | Track B |
|------|---------|---------|
| QMT 模拟盘 | `track_a/TrackA_track_a_qmt_full_chain_sim.py` **v2.17** | `track_b/TrackB_track_b_qmt_auction_sim.py` **v1.6** |
| QMT 实盘模板 | `track_a/TrackA_track_a_qmt_full_chain_live.py` **v2.17-tpl** | `track_b/TrackB_track_b_qmt_auction_live.py` **v1.6-tpl** |
| TDX 模拟盘 | `track_a/TrackA_track_a_tdx_full_chain_sim.py` **v2.15** | `track_b/TrackB_track_b_tdx_auction_sim.py` **v1.6** |

**本次修改涉及的函数**（6 文件一致）：
- `_t2_force_floor`（新增）、`_day_amplitude_pct`（新增）
- `_check_sell` 的 T+2 分支（改）
- 买入循环滑点保护（改）
- `_day_vwap`（QMT 4 文件改；TDX 2 文件已用快照 Average，不改）

**离线测试**（均通过）：
- `track_b/_test_sell_dynamic_v16.py` 9/9
- `track_b/_test_day_vwap_qmt.py` 4/4
- `track_b/_test_sell_rotation_v14.py` 10/10、`track_b/_test_rotation_v15.py` 9/9
- `track_a/_test_sell_rotation_v215.py` 11/11、`track_a/_test_rotation_v216.py` 9/9
