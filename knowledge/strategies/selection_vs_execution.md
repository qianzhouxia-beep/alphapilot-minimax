# 选股模型 vs 买卖模型（必须分开讲）

> 状态：**生产口径** ｜ 2026-08-28 用户定调  
> 以后出问题、改代码、写日志，先说是 **选股模型** 还是 **买卖模型**，不要混成「策略」。

## 一句话

**选哪只、排什么序 = 服务器上的选股模型。**  
**何时买、买不买得成、何时卖 = QMT / 通达信上的买卖模型。**  
日常改「选股」不用改交易端；日常改「买卖规则」才改 QMT/通达信。

## 对照表

| | **选股模型**（服务器） | **买卖模型**（QMT / 通达信） |
|---|---|---|
| 干什么 | 决定候选池和排名 | 决定这笔订单是否发、怎么卖 |
| 何时跑 | 05:00 管线、09:35 scanner、09:36 导出 | 盘中 09:35～14:57 逐 bar |
| 产物 | `daily_recommend.json` → `{date}.candidates.json`（Top10 顺序） | 成交、持仓、`*_trades_fullchain.json` |
| 代码在哪 | `live_momentum_scanner.py`、`morning_live_fund_select.py`、`export_qmt_scores.py`、V25 打分 | `production_strategies/track_a/`（及轨道 B 对应文件） |
| 典型问题 | 「网页 Top10 和买的票对不上」「池子只有 4 只」「融合权重」 | 「P2 一直 wait」「涨停 skip」「湖南黄金没买到」 |
| 你要不要改交易端 | **不用**（改服务器，复制 `candidates.json` 即可） | **要**（改 P2 / 仓位 / 止损才动 QMT、通达信） |

## 选股模型（服务器）

1. 05:00：`alphapilot_pipeline_v3.py` + V25 106 维打分 → 漏斗池  
2. 09:35：`live_momentum_scanner.py` 双路径重排（池 ≥100 池内重排；&lt;100 涨幅 Top~1000 资金轨）  
3. 09:35 后：`morning_live_fund_select.py` 资金门 / 研报门，按 score 写出 `recommendations` 顺序  
4. 09:36：`export_qmt_scores.py` **保序**导出 `{date}.candidates.json`（QMT/通达信只读这份）  
5. 09:38：`build_score_top10.py` 三路融合是 **网页展示榜**，**不是**买卖模型的下单顺序。2026-08-28 纸面回测：**不要**把该排名前移进 `{date}.candidates.json`（池内重排 Top2 T+1 相对现行序 -0.44pp）。详见 inbox `2026-08-28-fusion-web-rank-not-worth-forward.md`  

融合 IC（`fusion_scorer` / `model_weights.json`）调的是选股展示侧三路权重；**16:15 在服务器跑**。  
本机平仓写 `C:/alphapilot/fusion_closed_trades.jsonl`，工作日 **16:10** 任务 `scripts/sync_fusion_closed_to_server.py` 推到服务器，16:15 cron 才读得到。Linux 上的 `C:/alphapilot/...` 路径无效。  
**样本口径（2026-08-28 用户定调）**：轨道 A 的 QMT 实盘、QMT 模拟、通达信模拟 **通用**——同一套选股模型选出的票，三端平仓盈亏都进融合 IC，不要求「必须等实盘」。  
**不通用**：服务器纸面 `kelly_learner_trades.json`、RD `feedback_auto_tune`（scanner 因子 IC）、轨道 B 竞价选股。  

RD 的 `feedback_auto_tune.py` 是另一套选股因子 IC（ICIR/动量），**也不是买卖模型**。

## 买卖模型（QMT / 通达信）

读服务器已经排好的 `{date}.candidates.json`，**不再重新选股**：

- **2026-09-01**：只让 **rank 1-2** 进入 P2（`MAX_CAND_RANK=2`）。rank 3+ 不参赛、不触发换仓。  
- **同日**：关掉 Track A **rotation**（满仓踢最弱）。满 4 只就不再为新候选腾仓。  
- P2 动态确认（趋势 / 量比 / 不追高 / 换手 / ABR / 甜蜜区）——**资格收窄后仍要过 P2 才买**  
- 先到先得，每天最多买 2 只；两只都不过 P2 → 当天不买  
- 卖出：T+1 保护、止损、减仓、T+2 等  

这是 **candidates.json 的 09:35 顺序**，不是网页 09:38 融合 Top10。

**2026-08-28 已部署的交易端改动不是改买卖规则、也不是改选股。**  
只在买卖模型里加了 **记账**：买入记下三路分、卖出写入 `C:/alphapilot/fusion_closed_trades.jsonl`，给服务器选股模型的融合 IC 学习用。代码已复制到交易端，日常不用再手改。

## 轨道 B 例外（不要和轨道 A 混）

轨道 B 在 09:25–09:35 会在 **QMT/通达信上再做一轮竞价门控选股**（读 fullpool，不是只读 Top10）。那是轨道 B 自己的选股模型，跑在交易端。  
**本页默认口径是轨道 A**：名单和排名由服务器选股模型定完，交易端买卖模型不再重排。

## 出问题先问哪一层

| 现象 | 先查 |
|---|---|
| 候选名单 / 排名和网页、和预期不符 | **选股模型**（服务器 JSON） |
| 名单里有，但没买到 / 买了更后面的 | **买卖模型**（rank≤2 门槛、P2、涨停 skip、日限 2） |
| 买了但网页看不到 | 两套榜：选股导出 `candidates.json` vs 网页融合 `score_top10.json` |
| IC 权重有没有学到实盘盈亏 | 选股模型的 16:15 环 + 买卖模型是否写下 jsonl |

## 关联

- 09:35 选股双路径：`knowledge/strategies/0935_momentum_scanner.md`  
- 买卖规则：`knowledge/strategies/buy_sell_rules.md`  
- 生产文件：`production_strategies/`
- **Checkpoint 目录**（时间点表，含 08-28 融合 IC）：`knowledge/ops/checkpoints.md`
