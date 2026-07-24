# AlphaPilot V3 可交易方案（生产口径）

> 目标：真实可成交、可验收、可日常执行。不以「宽松金叉 + 涨停延续」刷高回测。  
> 完整管线逻辑 / 因子 / 可调参数：见 [`PIPELINE_V3.md`](./PIPELINE_V3.md)

## 1. 唯一上线臂

**A：`hard_strictGC_fund`（严格量价金叉 + 资金硬门控 + VM2.5 Top2）**

- 对照臂 B（soft 资金加权）仅作观察，不上线替换 A  
- 宽松金叉臂 C：**禁止上线**（涨停依赖强，不可成交）

## 2. 回测 / 验收协议（必须遵守）

| 步骤 | 规则 |
|------|------|
| 信号 | T 日收盘后，仅用 as-of 数据 |
| 候选 | **严格金叉**（价>MA25 且量 MA5 上穿 MA60） |
| 过滤 | 信号日已近涨停（≥涨停幅×0.97）→ 不进池 |
| 资金 | 近 5 日主力净额合计 > 0，否则剔除（硬门控） |
| 排序 | VM2.5 `score` 取 Top2（模拟盘日频 `paper_trading_signals.py` 对齐） |
| 买入 | **T+1 开盘**；开盘涨停/一字 → 不成交 |
| 卖出 | **T+2 收盘**（A 股 T+1） |
| 成本 | 双边合计 15bp（可按券商调整） |
| 成功 | 净收益 ≥ 3% |
| 风控指标 | 胜率 / hit≥3% / 日胜率 / **最大回撤** / 成交率 |

脚本：`backtest_v3_tradable_top3.py`（默认 `--top-n 2`，文件名历史保留）  
结果：`output/v3_tradable_top3_backtest.json`

## 3. 日常执行流程（Top2 可交易闭环）

1. 盘后更新 K 线、资金流（通达信近端 overlay + 长历史保留）  
2. 跑生产漏斗：`alphapilot_pipeline_v3.py`（严格金叉 → 资金硬门控 → VM2.5）  
3. 输出候选后 **人工/脚本再滤**：当日涨停附近不报、不买  
4. **09:35 盘中资金重排**：`morning_live_fund_select.py`  
   - 对 `daily_recommend` 池刷实时资金（同花顺即时 + 腾讯盘口资金门）  
   - 按**当日主力净流入**取前 **2** 只 → `output/morning_live_picks.json`  
5. **09:36 模拟盘**：`paper_trading_signals.py`（读 morning picks）→ `trade_executor.py`  
   - 开盘涨停/近涨停 → 跳过并记 `跳过(开盘涨停)`  
   - 仓位 = 策略资金池 × `position_exposure` × **等权 Top2**  
   - `expo=0`（nuclear）→ 不发买信号  
5. **盘中/次日**：`trade_executor.py --sell-only`；持有满 1 个交易日后 **T+2 强制卖**（止损/止盈可提前）  
6. **复盘**：`python3 scripts/audit_paper_tradable.py` → `output/paper_tradable_audit.json`  
7. **样本外验收**（训练截止日之后）：  
   `python3 scripts/run_oos_tradable_top2.py` → `output/oos_tradable_top2.json`  
   - 读取 `models/v25_meta.json` 的 `trained_at`，窗口从次日到今天  
   - 对照臂默认 `A1_ladder`（并报告 vs `A1_cur`）；未满 40 交易日 → `INSUFFICIENT_OOS`（不杠杆）

### 3.0 crontab（上海机，闭环自动化）

| 时间 | 任务 |
|------|------|
| 05:00 工作日 | `alphapilot_pipeline_v3.py`（产出池，薄仓最多 Top10） |
| 09:35 工作日 | `morning_live_fund_select.py`（池内实时资金重排 → 流入 Top2） |
| 09:36 工作日 | `paper_trading_signals.py` → `trade_executor.py`（买 Top2×expo） |
| 14:45 工作日 | `eod_s2_strategy.py` → executor（尾盘叠加，非主臂；距收盘约 15 分钟） |
| */10 9–14 | `trade_executor.py --sell-only`（止损/止盈；≥14:45 才 T+2 强制） |
| **16:10 工作日** | `scripts/audit_paper_tradable.py` |
| **周六 10:00** | `scripts/run_oos_tradable_top2.py` |

安装：`bash scripts/install_tradable_loop_cron.sh`  
API：`GET /api/v1/cn/paper-trading`（含 `loop.audit` / `loop.oos`）、`/paper-trading/audit`、`/paper-trading/oos`

可选增强（不改变主臂）：盘中 `soft_intraday_gate` 仅作分数微调，**不得硬删票替代资金硬门控**。

## 3.1 大盘指数环境门控 + 仓位

脚本：`market_env_gate.py`

| 条件 | 动作 |
|------|------|
| 创业板 / 科创50 **severe** | **硬过滤** 对应板 + 科技 L1 行业（电子/计算机/通信/传媒/军工） |
| **Permission Gate（生产默认）** | 见下表；脚本 `permission_gate.py` |
| （对照）阶梯 v2 | severe+crash→0；severe→0.25；见 `position_exposure_ladder` |

**Permission Gate（折中）**

| 条件 | expo |
|------|------|
| crash_day **且** 无 sustained_in **且** 涨≥3% 不足 50 | **0** nuclear |
| 许可 ON（涨≥3%≥100 或 ≥1 个 sustained_in）+ 指数正常 | **1.0** Top2 |
| 许可 ON + severe；涨≥3%≥200 | **0.5** |
| 许可 ON + severe | **0.25** Top1 |
| 许可 ON + weak/tech | **0.5** |
| 许可 OFF 但未 nuclear | **0.25** 地板（避免指数误杀） |

验收：`A1_permission` vs `A1_ladder`；maxDD 不差于 ladder 超过 +2pp。

**Permission Gate 验收（相对阶梯 v2，expo 不同的 9 个交易日）**

| 臂 | expo=0 日 | 成交 | 日均 | 总收益 | 胜率 |
|----|-----------|------|------|--------|------|
| A1_ladder | 3 | 4 | -0.005% | -0.04% | 25% |
| **A1_permission** | **1** | **7** | **+0.70%** | **+6.39%** | **43%** |

要点：2026-03-23 阶梯空仓、许可门薄仓日收益约 **+2.91%**；2025-04-08 许可门因宽度升到 0.5，日收益约 **+4.07%**。  
脚本：`scripts/_backtest_perm_vs_ladder_days.py` → `output/permission_vs_ladder_diff_days.json`。  
**生产默认已切到 Permission Gate**（`exposure_mode=permission_v1`）。

### 3.1.1 主臂 vs 弱势袖套（小仓）

| | **主臂 A1_ladder** | **弱势资金袖套 S1** |
|--|-------------|---------------------|
| 何时交易 | expo>0（含 0.25 薄仓） | **仅 nuclear expo=0**（研究臂，默认不下单） |
| 选股 | 严格金叉 + 资金硬门 + VM2.5 TopN | **3/5/10 日板块资金轮动** → 持续流入行业里选 Top1 |
| 仓位 | 1.0 / 0.5 / 0.25 | 固定小仓，默认 **0.25**（不叠在主臂薄仓上） |
| 目标 | 可交易收益 + 控回撤 | 跌市里「有没有该抓的 1 只」，对照空仓是否值得 |
| 脚本 | `alphapilot_pipeline_v3.py` / `paper_trading_signals.py` | `weak_fund_sleeve.py` |
| 验收 | `run_oos_tradable_top2.py` | `backtest_weak_sleeve_vs_empty.py` |

资金窗含义（轮动快时）：

- **3 日**：锋面（谁在抢）  
- **5 日**：骨架（是否站得住）→ 行业要 `sustained_in`（3日>0 且 5日>0）  
- **10 日**：防假流入（前面大出、只有短窗流入 → `pulse_in`，袖套不买）

```bash
# 今日袖套（仅主臂 expo=0 时出票）
python3 -u weak_fund_sleeve.py

# 空仓 vs 袖套对照（主口径：仅 severe）
python3 -u backtest_weak_sleeve_vs_empty.py --start 2026-01-16 --end 2026-07-15 --universe severe

# 探索：双市 weak 日并入（注意：这些日主臂仍可能半仓，空仓对照偏苛刻）
python3 -u backtest_weak_sleeve_vs_empty.py --start 2026-01-16 --end 2026-07-15 --universe both
```

**袖套 vs 空仓（资金流库覆盖 2026-01-16~07-15，可交易 T+1开/T+2收，袖套×0.25）**

| 宇宙 | 天数 | 袖套总收益 | maxDD | vs 空仓 | 结论 |
|------|------|------------|-------|---------|------|
| severe（主臂空仓） | 1 | **-0.75%** | 0 | 更差 | 样本极薄；暂不接入纸面 |
| both（severe∪market_weak） | 33 | **-4.48%** | 6.5% | 更差 | 当前规则不优于空仓 |

约束：`fund_flow_history` 仅约 120 个交易日；2025 年 severe 日无法复现资金窗。**未证明前不把袖套写入 09:36 买路径。**

验收脚本：`backtest_v3_tradable_gated.py` → `output/v3_tradable_gated_sleeve_backtest.json`  
OOS 包装：`scripts/run_oos_tradable_top2.py` → `output/oos_tradable_top2.json`

**2026-04-01~07-10 可交易对照（68 日）**

| 臂 | 胜率 | hit≥3% | 均收益 | maxDD | 总收益 | 备注 |
|----|------|--------|--------|-------|--------|------|
| A0 baseline | 63.7% | 46.1% | +2.45% | -19.7% | +363% | 原 A |
| A1 gated+仓位 | 63.2% | 42.6%* | +2.13% | **-16.4%** | +287% | 均仓位 0.87；7 月日均由 -2.16%→约 0 |

\*A1 的 hit≥3% 按仓位缩放后收益计；未缩放 raw hit≈45.6%。本窗口未触发空仓（无双指数 severe）。

## 3.2 板块资金轮动硬门控（行业骨架 + 概念锋面）

脚本：`sector_rotation_gate.py`（mode=`dual`）

| 行业状态 | 概念状态 | 动作 |
|----------|----------|------|
| deny | * | **拒绝** |
| * | deny | **拒绝** |
| allow | allow/neutral | **保留** |
| neutral | allow | **保留**（轮动锋面，多选潜力股） |
| neutral | neutral | **拒绝**（宁缺毋滥） |

原则：只过滤、不改分；高分弱势股照样剔除。

## 3.3 通达信映射

```bash
# 行业（F10 行业类别）
python3 scripts/build_stock_industry_map_tdx.py --concurrency 16
# 概念/题材（tdxf10_gg_rdtc zttzbkz）
python3 scripts/build_stock_concept_map_tdx.py --concurrency 20
```

- `data/stock_industry_map.json`
- `data/stock_concept_map.json`（已滤噪声标签：通达信88/大盘股/基金重仓等）
- 概念资金流缓存：`data/concept_flow_today.json` / `concept_flow_3day.json`

## 4. 验收门槛（未达标不上杠杆）

在可交易协议下，滚动 ≥40 个交易日：

- 成交率 ≥ 70%  
- hit≥3% ≥ 35%（或明显稳定优于同段随机 Top2）  
- 最大回撤可接受（建议监控，超过阈值降仓）  
- 样本外窗口尽量用训练截止日之后（当前模型 `trained_at=2026-07-18`，历史窗有 in-sample 风险）

## 5. 明确不做

- 不用宽松金叉刷 KPI  
- 不用收盘价假想买进已涨停票  
- 不把「次日涨停」算作稳定可复制收益  
- 不在 LLM 阈值未修好前用空输出污染验收  
