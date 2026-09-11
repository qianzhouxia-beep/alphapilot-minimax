---
project: alphapilot
domain: strategy
title: 增量因子扫描（量能/波动/板块三族）—— 正交但组合增量不稳健
date: 2026-09-10
status: observation
tags: [factor, incremental, partial-ic, portfolio, volatility, sector, turnover, negative-result]
---

# 增量因子扫描（三族 × 19 因子）

## 背景

老板 2026-09-10：`dma20` 新鲜度因子在**组合级回测不赚钱**（见 `2026-09-10-freshness-factor-discovery.md`），因为它与现有 gene 重叠。老板选 **"other_angle：找真正增量因子"**，并选**三族一起扫**。

**"增量"的定义**：与 gene（`rank(近10日涨停次数)+rank(MA25斜率)+rank(近10日收益)`）**正交**；检验口径=**控制 gene/rank 后的偏相关 IC** + **组合级影响**。

## 方法

- 面板：`kline_all.parquet`（含 `turnover`/`outstanding_share`/`amount`），2026-04 起；行业：`data/stock_industry_map.json`（覆盖 100%）。
- 因子（T-1 收盘，无前视）：**19 个**
  - **V 量能/换手**：turnover, turn_pct20, vr5, vr20, ar5, ar20, shrink_days, vol_5_20
  - **F 波动/形态**：amp, atr14, upper_sh, lower_sh, ret_std20, range_pos20, box20
  - **S 板块**：sec_ret20, rel_ret20, sec_breadth, sec_rank, sec_ret5
- 目标：`fwd1 = close(T+1)/open(T)-1`；`hit3_t1 = high(T+1) ≥ open(T)*1.03`；`fwd5`。
- 检验：①裸 Spearman IC；②**控制 rank / gene 的偏相关 IC**（秩回归残差）；③组合级（基线=rank Top2，出场=`abs3_trail`+止损）；④**前后半段稳健性**。
- 脚本（服务器 `bt_research/`）：`bt_factor_zoo.py`（筛选）、`bt_factor_zoo_portfolio.py`（组合+半段）。

## 发现 1：这些因子**确实正交**（偏 IC ≈ 裸 IC）

与 `dma20`（被 gene 吃掉）不同，本批因子的偏 IC 几乎等于裸 IC，说明 rank/gene 没解释掉它们。

| 因子 | 族 | 偏IC(控rank) | +3%命中 lift(Q5−Q1) | 方向 |
|---|---|---|---|---|
| **range_pos20** | 形态 | **−0.200** | −0.111 | 20日区间内**越低越好** |
| **sec_ret20** | 板块 | **−0.175** | −0.167 | 板块**越热反而越差** |
| **sec_breadth** | 板块 | −0.165 | −0.148 | 板块广度越高越差 |
| lower_sh | 形态 | −0.153 | −0.075 | 下影线越长越差 |
| vol_5_20 | 量能 | −0.111 | −0.019 | 放量越猛越差 |
| **atr14** | 波动 | +0.090 | **+0.296** | 波动大→+3%命中高 |
| **ret_std20** | 波动 | +0.078 | **+0.315** | 同上 |
| **box20** | 形态 | +0.068 | +0.278 | 箱体越宽越易摸+3% |
| **shrink_days** | 量能 | **+0.077** | +0.074 | **缩量整理越久越好** |

两个亮点：**① 波动族强预测 +3% 命中**（与"锁+3%"出场天然互补）；**② `shrink_days`（缩量整理天数）正 IC 且正交**——是老板"低位横盘"的量化代理，全新维度。

## 发现 2：组合级有几个"看起来加分"（全窗口）

基线（rank Top2）+4.55%。最好：

| 变体 | 总收益 | 胜率 | vs 基线 |
|---|---|---|---|
| B_blend:vol_5_20 | +6.43% | 67% | +1.88 |
| F_filter:atr14 | +5.97% | 65% | +1.42 |
| F_filter:range_pos20 | +5.57% | 63% | +1.02 |

但**同一因子在不同集成方式（filter vs blend）符号会翻**（range_pos20 filter +1.02 / blend −1.06）→ 噪音嫌疑。

## 发现 3（关键）：**前后半段无一通过**

基线 H1 +5.17% / H2 −0.59%。**20 个变体的 `both?` 全部为 `-`**：

- `B_blend:box20`：H1 +10.09%(+4.92) / H2 −5.25%(−4.66) —— 单半驱动典型
- `F_filter:atr14`：H1 +6.62%(+1.45) / H2 −0.61%(−0.02) —— 最接近，H2 基本持平

**结论：全窗口的加分不稳健，由某一半驱动。**

## 结论（勿混）

- ✅ **筛选层**：三族里确实存在**与 gene 正交**的因子（波动族、`range_pos20`、板块动量/广度、`shrink_days`）。
- ❌ **组合层**：在 30 天 / 54 笔窗口内，**没有任何因子通过前后半段稳健性** → **不足以改选股，暂不上**。
- ⚠️ **方法学**：n=54 的组合级因子检验**功效严重不足**；半段各 ~27 笔，噪音主导。**扩大样本前不要据此下结论（无论正负）。**

## 下一步（待老板定）

- A. **扩样本再判**：现有候选归档仅 ~30 天。要么等积累，要么用 `qmt_scores/*.candidates.json`（24 天）合并，仍不够 → 建议**先做全市场 19 个月 IC triage**（高功效）把因子分真伪，再等候选池样本够。
- B. **只保留筛选层结论**：把"波动族 + 缩量整理"作为**观察项**登记，不改任何代码。
- C. 转向**非因子杠杆**（老板此前认可"选股端 gene 重排是大杠杆"）——重新设计 gene 本身，而非叠加因子。

## 链接

- 脚本：`bt_research/bt_factor_zoo.py`、`bt_research/bt_factor_zoo_portfolio.py`
- 输出：`output/bt_factor_zoo.json`、`output/bt_factor_zoo_portfolio.json`
- 相关：`2026-09-10-freshness-factor-discovery.md`
