---
project: alphapilot
domain: data
title: 资金三角影子空转 9 天已补传+历史回放补偿（因子方向支持保留）— 09-06 复盘+回撤
date: 2026-09-06
status: conclusion
tags: [shadow, fund-bonus, 资金三角, 部署缺口, 静默失败, 回放, 复盘, 换手影子]
---

# 结论（更新 2026-09-06 晚间：已补传 + 历史回放完成）

- 09-06 15:40 复盘发现：资金三角影子模块 `fund_bonus_shadow.py`（连同 market_regime/sector_quality）**从未上传服务器** → 08-25~09-04 九交易日全部静默 skip，实时样本 0。同批 `market_regime_shadow`(9 skip)/`sector_quality_shadow`(3 skip) 一并缺失。属"部署缺口非写码缺口"，且是又一起静默失败（只有一行 soft log、无告警）。
- 老板追问"是否已部署在 live"→ 全仓核查：morning_live_fund_select.py（09:35 生产/live 链）是唯一引用点，纯只读 shadow hook，从未加分/改序；live 端与生产链同态空转。
- **补救一（补传）**：09-06 已 scp 三模块到服务器根目录，import 冒烟通过 → 09-07 周一 09:35 起真积累。
- **补救二（历史回放补偿，bt_research/replay_fund_bonus_shadow_report.md）**：用 daily_picks_archive 九日 top10_gated∪ungated 候选池（~113 行）+ 同款三因子 + 同口径(T0收盘买/T+n收盘卖)结算。主结果（候选空间内 bucket，规避双时刻分污染）：
  - any_hit T+1 **-0.10%**(n=50,胜48%) vs no_hit **-1.02%**(n=45,33%) → **+0.92pp**
  - any_hit T+5 **-0.53%**(n=27) vs no_hit **-2.18%**(n=19) → **+1.65pp**
  - 单因子：**c2(连续流入)两期皆优**(T+1 +0.77pp / T+5 +3.0pp，最可信)；**hot T+1 强**(+1.35pp)但样本小(n=7)、T+5 不稳；**mild(5日小涨)基本无效、T+5 反向**(-1.48pp)。
  - 9 天市场弱：候选池整体 T+1 ≈ -0.54%，命中只是"少亏"。
  - 结论：**两周没完全白费**，三角因子在候选空间有区分度、方向支持保留；建议真影子 2-4 周后复核，重点盯 mild 是否拖后腿（若确证无效建议权重 0.04→0，需另拍板）。

## 1. 资金三角影子（08-22 决定 / hook 在 `morning_live_fund_select.py`，默认开）→ 复盘时空转；已补传+回放

- hook 在 09:35 主链路内：`FUND_BONUS_SHADOW` 默认开 → `from fund_bonus_shadow import write_shadow`（写 `output/fund_bonus_shadow.jsonl`，因子=热板块+0.06 / 5日小涨+0.04 / 连续2日流入+0.08 / 三合一+0.04，cap 0.15）。
- **模块 `fund_bonus_shadow.py` 在服务器不存在**（根目录与 /home/ubuntu 全域 find 均无）→ 每个交易日 09:35 落 `fund-bonus shadow skip: No module named 'fund_bonus_shadow'`。
- skip 计数 = **9 次（= 9 个交易日，首跑 ~08-25 / 末跑 09-04，l2_refresh.log 上下文可对上）** → 影子文件从未创建 → **积累 0 天 / 样本 0 / 无 T+1·T+5 结算可算**。
- 同批缺口：`market_regime_shadow.py`（9 skip）、`sector_quality_shadow.py`（3 skip）也在服务器缺失。其余 5 个影子模块已上传且在积累：wind_regime(2)/weak_score(2)/live_tone(2)/market_flow_condition(2)/vp_factor(09-04 上传)。
- 本地仓库根目录**都有**这三份模块（`fund_bonus_shadow.py` 等均 untracked，从未 push/上传）→ 这是**部署缺口不是写码缺口**。服务器依赖齐备（consec_inflow.py、data/stock_industry_map.json、data/kline_cache/kline_all.parquet 均在）。
- 危害性质：**静默失败** —— try/except 吞掉 + 仅一行 soft log，无任何告警；若没人主动对账，会一直"以为在攒样本"直到复盘才发现 0 积累。这正是本系统老毛病的又一例（与 8 月初 sector_flow_5day 断更同族）。

## 2. 聚宽换手影子（08-30 上线 / cron `20 22 * * 1-5` / `rd_workshop/shadow_turnover_daily.py`）→ ✅ 健康但未达纳入门槛

- `shadow_log.csv` 5 行（08-28 种子于 08-30 手工回填 + 08-31/09-01/09-03/09-04）：baseline 106 维 vs plus 108 维（+`rd_turnover_ratio`,`rd_turnover_vol_ratio`），**diff 全正** +0.0016 / +0.0014 / +0.0016 / +0.0017 / +0.0021，双跑耗时 66~72min。
- **09-02 晚 plus 阶段"训练超时 >2400s"**（cron 日志 23:29:52 ❌）→ 当日无 CSV 行；脚本 09-03 00:29 修复（mtime）。**修复后 09-03/09-04 连续 2 次健康**。
- 门槛判定：要求"连续 5-10 日 diff≥0"→ 被 09-02 缺口打断，目前**仅 2 连，未达标**；乐观最早 09-09（再攒 3 个连续交易日）达标。
- 无静默失败：cron 日志每行带时间戳、记录 启动/因子表/双跑完成/超时/✅记录，与 CSV 一一对应。
- 一致性佐证：09-02/03/04 换手影子 baseline AUC(0.7168/0.7159/0.7159) 与 daily_retrain new_auc 同日相等 → 确认走的是与生产同款 106 维滚动重训，非玩具。

## 3. daily_retrain AUC 闸门（21:30 cron）→ 09-02 后从未放行

- 09-02 diff -0.0053 拒 / 09-03 -0.0062 拒 / 09-04 -0.0062 拒；往前 08-25 起也全拒（-0.0038~-0.0154）。old_auc 恒 0.7221（模型冻结 08-21）→ 生产模型保持旧版。09-07 21:30 下次重训。

## 动作建议

1. ~~补传 3 模块~~ **已完成（2026-09-06 晚间）** → 09-07 09:35 起真积累。
2. 治本：给"影子模块缺失/静默 skip"加告警（例如 daily health check 里核对每模块输出文件昨日 mtime），避免同类再次静默。
3. 换手影子继续攒至连续 5+ 日再谈纳入；期间盯是否还有超时。
4. 真影子 2-4 周后复核本回放 bucket 方向；重点盯 mild 是否拖后腿（确证无效则权重 0.04→0，需另拍板）。
