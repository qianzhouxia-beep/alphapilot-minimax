---
project: alphapilot
domain: strategy
title: 回撤触发的"二次确认"要不要加？分强弱市回测 —— next_bar 全市场有效，慢确认只在强市（且不稳定）
date: 2026-09-10
status: conclusion
tags: [sell-model, peel, trail, pullback, second-confirmation, regime, market-breadth, track-a, backtest]
---

# 回撤触发的二次确认（二次回踩）分市况回测（2026-09-10）

## 问题（老板原话要点）
生产 peel（TrackA v2.44）在 `ret>=+3%` 后武装 peak-pullback trail，**首次**触及 `trigger=peak*(1-pb)`（pb≈1.5~2%）就卖一半，**无二次确认**。老板问：
1. **弱势市场**：首次触及就卖（现状）对不对？
2. **强势市场**：加一个**二次确认（二次回踩）**是否更合理？

## 结论（一句话）
**"二次确认"在强弱市都跑赢首次触及，且强市赢得更多一点点 —— 所以老板的方向对，但"弱市该保持首次触及"这半句不成立。** 真正稳健的只有最便宜的一档确认（`next_bar`：第一次触及只"武装"，下一根 5m K 也破 trigger 才卖），弱市 +0.50pp、强市 +0.58pp（powered n≈2.4 万，t≈36~49）。**慢确认**（连续两根收破 / 收破确认 / 回抽后再破）在弱市是负的、强市微正，但**随时间段翻转**（前半段两个市况都为正，后半段都为负）→ 不能当作稳定的市况效应。

## 方法
脚本 `bt_research/bt_exit_confirm_regime.py`（本地 + 服务器同名）。
- 同一条 trail 逻辑：`high>=entry*1.03` 武装 → 跑 running peak → `trigger=peak*(1-pb)`，pb=1.5%；**A股 T+1 锁**，出场只在 T+1..T+3 的 5m bar。
- 变体：`first`（现状）／`first_nsb`（不允许"武装当根就触发"，robustness）／`next_bar`／`two_close`（连续两根收破）／`close_confirm`（收破即卖，影线不算）／`rebound_second`（触及→收回 trigger 上方→再次破）／`delay1~3`（纯等待成本）。全部**带 -4% 硬止损**（另有不带止损的敏感版）。
- 两个样本：
  - **candidate**：真实选股档案 `output/daily_picks_archive/*/top10_ungated.json`，T 09:40 开盘进场，T+1..T+3 出场，`usable=263/297`。
  - **powered**（统计功效用、**代理样本**）：`powered_open` 全市场任一"日内高≥09:40 开盘×1.03"的日子（entry=09:40 开盘，n=29438）；`powered_cross` 按老板要求"首次突破 +3% 那根 bar 的开盘价进场"（n=33203）。均要求日成交额≥1 亿、剔除离涨停太近的进场。
- **市况**：`kline_all.parquet` 等权全 A 计算（面板**无指数行**）：`breadth` = close>MA20 的占比（中位数切分为主，三分位为辅）；`mkt5` = 等权 5 日收益 >0。**判定用"前一个已收盘交易日"（lag1，严格无未来函数）**，同日口径（lag0）作敏感版；两口径结论一致。
- 统计口径：所有变体在同一"首次触及"事件集上比较（条件于该次回撤确实发生）。mean/median/win/p5/p95 全量存 JSON。

## 结果 A：真实候选池（candidate，touch n=158）
市况 = breadth 中位数（lag1），含 -4% 止损：

| variant | 弱市 n=57 mean% | win | Δvs first | 强市 n=101 mean% | win | Δvs first |
|---|---|---|---|---|---|---|
| **first（现状）** | 3.58 | 88% | 0.00 | 3.31 | 89% | 0.00 |
| first_nsb | 3.92 | 88% | +0.33 | 3.61 | 88% | +0.30 |
| **next_bar** | **4.10** | 88% | **+0.52** | **3.76** | 88% | **+0.45** |
| two_close | 3.67 | 81% | +0.09 | 3.24 | 85% | −0.07 |
| close_confirm | 3.71 | 84% | +0.13 | 3.12 | 86% | −0.19 |
| rebound_second | 3.20 | 75% | −0.38 | 3.58 | 81% | +0.27 |
| delay1 | 3.89 | 81% | +0.30 | 3.41 | 86% | +0.11 |

`mkt5` 口径弱市 n=35 / 强市 n=123：next_bar **+0.47 / +0.48**，其余同向。n=57/101，单看 candidate 达到常规显著（t≈4.0/3.3，配对），但样本仍薄。

## 结果 B：功效样本（powered，代理进场）

### B1 `powered_open`（entry=09:40 开盘，touch n=24190），breadth 中位数 lag1，含止损
| variant | 弱市 n=10157 mean% | win | Δ | 强市 n=14033 mean% | win | Δ |
|---|---|---|---|---|---|---|
| **first** | 3.85 | 93% | 0.00 | 4.34 | 96% | 0.00 |
| first_nsb | 4.24 | 93% | +0.39 | 4.79 | 96% | +0.45 |
| **next_bar** | **4.35** | 93% | **+0.50** | **4.93** | 96% | **+0.58** |
| two_close | 3.76 | 90% | −0.09 | 4.52 | 93% | +0.18 |
| close_confirm | 3.85 | 92% | +0.01 | 4.47 | 94% | +0.13 |
| rebound_second | 3.78 | 84% | −0.07 | 4.52 | 88% | +0.18 |
| delay1 | 3.81 | 90% | −0.04 | 4.39 | 93% | +0.05 |

`mkt5` 口径（弱 n=5454 / 强 n=18736）：next_bar **+0.39 / +0.60**；two_close **−0.38 / +0.20**；close −0.22/+0.17；rebound −0.13/+0.14；delay1 −0.30/+0.10。
三分位（breadth）：next_bar 弱 +0.53 / 中 +0.44 / 强 +0.64（单调）。

### B2 `powered_cross`（entry=首次突破 +3% 那根的 open，touch n=23779），breadth 中位数 lag1，含止损
| variant | 弱市 n=10345 mean% | win | Δ | 强市 n=13434 mean% | win | Δ |
|---|---|---|---|---|---|---|
| **first** | 3.82 | 91% | 0.00 | 4.20 | 94% | 0.00 |
| first_nsb | 4.22 | 91% | +0.40 | 4.64 | 94% | +0.44 |
| **next_bar** | **4.35** | 91% | **+0.53** | **4.78** | 94% | **+0.58** |
| two_close | 3.82 | 87% | −0.00 | 4.34 | 91% | +0.13 |
| close_confirm | 3.83 | 89% | +0.01 | 4.28 | 92% | +0.08 |
| rebound_second | 3.84 | 83% | +0.02 | 4.32 | 86% | +0.12 |
| delay1 | 3.77 | 88% | −0.04 | 4.22 | 91% | +0.01 |

`mkt5`：next_bar **+0.45 / +0.59**；two_close −0.21/+0.15。三分位：next **+0.54 / +0.46 / +0.64**；two_close **+0.05 / −0.26 / +0.32**；rebound **−0.00 / −0.25 / +0.35**。

### 三样本一致的量化结论
| 口径 | 弱市 | 强市 | next_bar 相对 first |
|---|---|---|---|
| candidate | +0.52 | +0.45 | 全样 +0.48（t≈5） |
| powered_open | +0.50 | +0.58 | 全样 +0.55 |
| powered_cross | +0.53 | +0.58 | 全样 +0.56（t≈58） |

next_bar 在所有市况定义、lag0/lag1、带/不带止损、两个样本里**全部为正**，t=20~58，**胜率几乎不变**（93%→93%、94%→94%、candidate 89%→88%）——增益来自均值/尾部，不是提高命中率。

## 关键 caveat：增益里"二次确认"本身只占一小半
`first`（允许"武装当根就触发"）→ `first_nsb`（不允许）已经有 +0.30~+0.45pp。这部分是 **5m 粒度伪影**：同一根 5m bar 内先 +3% 再回撤到 trigger，实盘 tick 级未必发生（真实生产行为更接近 `first_nsb` 而不是 `first`）。
所以老板提案的**诚实增量**是 `next_bar − first_nsb`：candidate +0.18/+0.15，powered_open +0.11/+0.14，powered_cross +0.13/+0.14（弱/强）——**+0.1~0.2pp，稳健但很小，且无市况差异**。而 `delay1`（纯等一根）在弱市是 −0.04~−0.30，说明这 0.1~0.2pp 不是"等待成本"，是"下一根继续破位"的信息量。

## 慢确认（two_close / close_confirm / rebound_second）为什么不能当市况结论
汇总看确实"强市正、弱市负"，但**按进场日对半切**后：

| powered_open，breadth 中位数，Δvs first | H1（≈07-23~08-14） | H2（≈08-14~09-09） |
|---|---|---|
| 弱市 next_bar | +0.62 | +0.41 |
| 强市 next_bar | +0.69 | +0.45 |
| 弱市 two_close | +0.22 | −0.36 |
| 强市 two_close | +0.51 | −0.26 |
| 强市 rebound_second | +0.68 | −0.49 |

强市日**集中在 H1**（7 月底~8 月中 breadth 冲到 0.90），H2 想找强市已经很少 → 慢确认的"市况效应"与"时间段"高度混淆：**在两个市况里都是 H1 正、H2 负**。只有 next_bar 在四个格子里全部为正、且强市恒 ≥ 弱市约 0.05~0.15pp。

## 判定
- **弱市：不是 `first` 最好。** 最便宜的二次确认（`next_bar`）在弱市同样 +0.50pp（three power samples 一致）。若只在"慢确认"里选，则弱市 `first` 确实优于 two_close/close_confirm/rebound_second。
- **强市：二次确认更值钱一点点**（next_bar +0.58~+0.64，且三分位单调），但增量幅度只比弱市大 0.05~0.2pp；**不是"弱市不用、强市才用"的开关式差异**。
- **不建议**上 two_close / rebound_second 这类慢确认——市况效应不稳定、时间段一翻转就变负，且胜率掉 3~8pp。

## 局限（勿隐藏）
- 窗口仅 **35 个交易日**（2026-07-23~09-09），且强市日时间聚集 → 市况与时间段混淆（已用半样本揭示）。
- powered 两个样本是**代理进场**（非真实策略成交，cross 版进场价还有"盘中才知道突破"的轻微乐观），只看方向不看幅度。
- 5m bar 只有 high/low，**看不到 bar 内路径**；同根既碰 -4% 止损又碰 trigger 时统一按**止损优先**；`trigger` 成交假设按 trigger 价、收破类按收盘价成交，**未计滑点/手续费**。
- 生产只卖**一半**仓位，因此实际账户影响约为上述数字的一半（本次按整仓口径比较）。
- 条件于"首次触及确实发生"（candidate 158/263，powered 约 82% 的事件）；未触及的事件各变体完全相同，不影响 Δ。
- 仅测 pb=1.5%；仅等权 breadth/mkt5（面板无指数行）；regime 用 lag1 为主、lag0 结论一致。

## 证据
- 脚本：`bt_research/bt_exit_confirm_regime.py`（本地 `/Users/AlphaPilot/bt_research/bt_exit_confirm_regime.py`；服务器 `/home/ubuntu/alphapilot/bt_research/bt_exit_confirm_regime.py`）
- 结果：`/home/ubuntu/alphapilot/output/bt_exit_confirm_regime.json`（62904 events，含全部表格与逐事件收益；服务器运行日志 `/tmp/confirm_full.log`）
- 基线对照：`bt_research/bt_exit_schemes.py` / `output/bt_exit_schemes.json`（本脚本 candidate usable=263 与其一致）
- 生产现状：`production_strategies/track_a/TrackA_track_a_qmt_full_chain_sim.py` v2.44（首次触及即卖一半，无二次确认）
