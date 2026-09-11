---
project: alphapilot
domain: architecture
title: 港股/美股纸盘框架 v1 落地（新加坡）
date: 2026-09-10
status: conclusion
tags: [hk, us, paper-trading, framework, singapore, phase0]
---

# 港股/美股纸盘框架 v1（2026-09-10 Cursor）

## 一句话
Phase 0 从"地图 + 数据地基"升级为**可运行的框架实体**，部署在新加坡 `/home/ubuntu/alphapilot/hk/`，HK 先行、US 留同接口，可日更。

## 模块
```
config.py        配置：路径/成本/权重/池阈/持仓参数
dataio.py        UA-aware HTTP + 原子 JSON 写 + 交易日历
sources.py       抓取 K线(HK/US) / 南向持股截面(WAF安全filter) / 建池
factors.py       因子注册表 + 价格族(mom20/60/120, trend_ma20, vol20, dd60) + 南向族(ratio_chg5/20, shares_g5/20, ratio_lvl)
signals.py       透明加权打分(横截面 z-score×方向×权重) + 闸门
paper.py         交易成本(HK印花0.1%双边) + 纸盘引擎(事件循环/ledger/equity)
daily_update.py  日更管线：K线→南向→建池→readiness(→picks)
run_paper.py     回放/基线
```
打分刻意透明（Phase-1），不先上 ML。南向因子默认 `dir=-1`（已实证为反向/风险信号）。

## 时序与成本
- T 收盘算信号 → T+1 开盘买（滑点）→ 持有 `HOLD_DAYS=5` → 到期日收盘卖（滑点）
- 与南向 IC 口径一致（D+1 open → D+1+H close）；南向 T+1 披露滞后内置（`Context.south_asof` 严格早于打分日）
- HK 费用：印花税 0.1% 双边 + 佣金(最低) + 平台费；US：SEC 费(仅卖)+佣金

## 现状（2026-09-10 11:34 实测）
- SG `/home/ubuntu/alphapilot/hk/`：`data/{kline.json(608×200d), southbound_hist.json(66截面日), pool.json(448)}`、`output/{readiness.json, picks_2026-09-09.json, paper_*}`
- `daily_update.py --picks` 实跑：南向自动补到 **09-09**、池 448、`readiness.ready=true`、picks 已出
- 回放基线（07-09→09-09，62 笔）：总收益 **-18.3%**、胜率 42%、均值 -2.96%（7月动量崩盘段 -8.2%/月，8月回正）
  → **诚实基线：默认透明因子+反向南向组合是亏的**，正说明框架可用于快速证伪；后续填因子/调权迭代

## 待办
- [ ] 装日更 cron（README 已给，两次：17:20 拉K线 / 09:10 补南向+选股）
- [ ] readiness 接入既有告警巡检
- [ ] 质量因子（ROE/负债）需基本面源
- [ ] 美股池 + 美股因子（接口就绪）
- [ ] 券商沙盒接线（富途/老虎/Alpaca）

## 因子调优（2026-09-10 11:40，`_factor_ic.py`）
全池 448、fwd5 横截面 Spearman IC 体检：

| 因子 | meanIC | t | 判定 |
|---|---|---|---|
| vol_20（低波） | -0.092 | **-5.5** | ✅ 强（港股奖励低波/防御） |
| dd_60（小回撤） | +0.086 | **+5.1** | ✅ 强且 split-half 稳定 |
| sb_shares_g5（南向反向） | -0.050 | **-4.8** | ✅ 但 8 月衰减 |
| sb_ratio_chg5 | -0.035 | -3.2 | ✅ |
| mom_20/60/120（动量） | +0.011~0.027 | 1.2~1.5 | ❌ **不显著** |
| trend_ma20 | +0.014 | 1.5 | ❌ 不显著 |

原默认权重把 ~45% 押在动量 → 押错。重定权重（只留 |t|≥2 的 5 因子，方向取符号）后回放：

| | 默认权重 | 调优权重 |
|---|---|---|
| 总收益 | **-18.3%** | **+10.2%** |
| 胜率 | 42% | 51% |
| 最差单笔 | -46% | -7% |

**诚实警告**：样本仅 2 个月；`dd_60` 本身是"事后强势"因子，天然偏高；需更长窗 + 样本外验证，**勿当定论**。防御型因子在动量崩盘段有天然优势，可能是 regime-specific。

## 关联
- 设计蓝图：`knowledge/inbox/2026-09-09-hk-us-paper-sim.md`
- 数据探测/坑：`knowledge/inbox/2026-09-10-hk-us-phase0-probe.md`
- 南向 IC 结论：`knowledge/inbox/2026-09-10-southbound-factor-ic.md`
- 本地副本：`bt_research/hk_framework/`（含 `_test/` 测试数据）
