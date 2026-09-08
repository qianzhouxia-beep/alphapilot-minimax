# WorkBuddy 任务单：回撤分析 research（Mac）

> 派给：Mac 上的新 WorkBuddy  
> 日期：2026-09-02  
> 层：**买卖模型 research**（只写 `bt_research/` + 知识卡，**禁止改** `production_strategies/`）  
> 背景：QMT 实盘 08-28 起几乎全是亏损离场。主电脑 Cursor 已归因「买到 rank 4–10」，止损多数卖后继续跌。需要你把「回撤」从体感变成可复核的数字。

读完本文先回三句话：仓库是否已打开、本机有没有 `data/kline_cache/kline_all.parquet`、今天先做哪一张票。

---

## 0. 开工前

1. 仓库必须打开。没有仓库就停，不要凭印象编回测。远程 `https://github.com/qianzhouxia-beep/alphapilot-minimax.git`；若 CHANGELOG 最新条还早于 2026-09-02，先告诉用户远程落后，不要当权威。
2. 本机是 macOS：现有脚本里的 `C:\Users\elvisq\...`、`C:\alphapilot\` **不能用**。新脚本用仓库相对路径。
3. **不要改生产策略，不要传筹码，不要连交易端，不要要密钥。**
4. PASS 静默。只在 FAIL、口径对不上、或得出「建议改生产」时主动报（改生产必须等人拍板，你只出数字）。

必读（按需，不要读全库）：

- `knowledge/ops/checkpoints.md` 最上 15 行
- `knowledge/inbox/2026-09-02-live-week-only-loss-exits.md`
- `knowledge/inbox/2026-09-02-three-day-live-loss-root-cause.md`
- `knowledge/inbox/2026-09-02-holdings-4x20-beats-3x30.md`（**不要重做 3×30**）
- `bt_research/wb_portfolio_drawdown.py`（已有：生产 Top2、D 日 open 买、T+1/T+2 纸面 NAV）
- `bt_research/bt_sell_stats_report.md`（已有：peel / t2_force / hard_stop 分原因，日线近似）

已有结论，**不要重复劳动**：

- 4×20% 优于 3×30%（本窗口 maxDD −8.35% vs −6.48%，收益差更大）
- 峰值回撤 6% 当止损是最差卖法（delta −5.58%）
- Dual Thrust 不适合 A 股
- 网页融合排名不前移

---

## 票 1 — 实盘第一周：路径回撤 vs 实现回撤（先做）

**问题：** 08-28～09-02 QMT 实盘 5 笔平仓，卖的时候都在亏（天齐 +47 忽略）。这些票在持有期内最深亏到哪（MAE）、最好时到过哪（MFE）？卖飞了没有？

**样本（实盘成交，不要用网页 Top10）：**

| 标的 | 买 | 卖 | rank | 原因 |
|---|---|---|---|---|
| 002058 紫竹 | 08-28 @ 17.5645 | 08-31 14:22 @ 17.04 | 8 | rotation |
| 002466 天齐 | 08-28 @ 49.6625 | 08-31 14:45 @ 49.78 | 10 | t2_after_extend |
| 300390 天华 | 08-31 @ 64.6467 | 09-01 14:45 @ 61.98 | 7 | t2_force |
| 300475 香农 | 08-31 @ 171.86 | 09-02 09:36 @ 165.62 | 4 | vwap_weak_early |
| 000751 锌业 | 09-01 @ 5.3714 | 09-02 14:45 @ 5.16 | 6 | t2_force |

仍持仓（算到 09-02 收盘，不当平仓）：002212 成本 6.7117；002291 成本 6.0518；002437 成本 4.5913。

**要交的数字（每笔）：**

- MAE：持有期内最低价相对成本 %
- MFE：持有期内最高价相对成本 %
- 是否曾到过 +3%（生产 peel 武装线 `DEF_TRAIL_ARM=0.03`）
- 卖出价 vs 卖后当日收盘、vs 09-02 收盘（卖飞 / 卖对）
- 若「卖出日不卖、拿到 09-02 收盘」盈亏差多少

**数据：** 本机若没有全市场 parquet，用东财日线 + 5 分钟（仅上述 8 只）即可。不要为这张票去拷 5000 只 K 线。

**产出：** `bt_research/wb_dd_live_week_mae.py` + `output/wb_dd_live_week_mae.json` + inbox 卡。  
结论必须回答一句：**这周的回撤，主要是「票本身走弱」还是「卖点把回撤锁死」？**

---

## 票 2 — rank 尾部 vs Top2：谁在制造组合回撤（主研究）

**问题：** 组合最大回撤，有多少来自「买了 candidates rank 3–10」，多少是 Top2 自己也会有的？

**口径（必须写进报告）：**

- 名单：真实 `{date}.candidates.json`（`bt_research/_cmp/qmt_scores/`，不足再说明缺哪几天）
- 窗口：能拿到的最长连续 09:35 名单（至少覆盖 2026-07-26～09-01；有 08-28 更好）
- 组合 A：每天 rank 1–2，日限 2，最多 4 槽 × 20%，**不开 rotation**，T 收盘买 / T+2 收盘卖，双边 15bp（与 `bt_holdings_3vs4_rank2.py` 对齐，便于对照）
- 组合 B：每天 rank 3–10 里「先到先得」的代理——**不要假装能复现 P2**。代理用两种都跑，并排：  
  - B1：每天买当日 rank 中编号最大的 2 只（最弱两名）  
  - B2：每天买 rank 3 和 4  
- 组合 C：旧实盘近似：每天从 rank 4–10 抽 2 只（固定规则，例如 rank 5+8，或按 score 最低的两只）。选一种写死，不要随机。
- 输出每个组合：总收益、Sharpe、**maxDD**、maxDD 日期、回撤持续天数、满仓跳过比例

**不要：** 重做 4×20 vs 3×30。仓位固定 20%。

**产出：** `bt_research/wb_dd_rank_tail_vs_top2.py` + `output/wb_dd_rank_tail_vs_top2.json` + inbox。  
结论必须回答：**若实盘从第一天就只买 rank≤2，这个窗口的 maxDD 会小多少、收益差多少？**  
附一句局限：没有 P2，纸面会高估成交。

无 parquet 时：只拉 candidates 里出现过的代码的日线（大约几十只 × 窗口），不要全市场。

---

## 票 3 — t2_force 在 T+1 开火，会不会加深回撤？

**问题：** 实盘天华、锌业都是 **T+1 的 14:45 地板**。有人会想「改成 hold_days≥2 再 t2_force」。这对组合回撤是减还是加？

**口径：**

- 样本：票 2 的组合 A（rank≤2）和组合 B2（rank 3–4），同一窗口
- 规则 1（现状代理）：T+1 收盘若亏损超过 −3.5% 则卖（近似动态地板；再加一档 −2.2% 做敏感性）
- 规则 2：T+1 不卖，T+2 收盘再看同一地板
- 规则 3：全程拿到 T+2 收盘，无地板（对照）
- 每笔记录：T+1 是否触发、触发后到 T+2 收盘是继续跌还是反弹

**产出：** `bt_research/wb_dd_t2_force_t1_vs_t2.py` + json + inbox。  
结论必须是三选一，并带样本数：

- 「T+1 地板在减回撤」（触发后继续跌为主）  
- 「T+1 地板在加大回撤」（触发后反弹为主，类似香农）  
- 「对 maxDD 无显著差，不要改生产」

**默认预期：** 主电脑已有「卖后继续跌」的实盘 4/5 笔。你要用更长名单验证，不要用 5 笔实盘当结论。

---

## 交付格式

每张票结束时：

1. 脚本 + `output/*.json`（可复跑）
2. 全局 inbox：`knowledge/inbox/YYYY-MM-DD-wb-dd-<短横线>.md`（frontmatter 按 `_TEMPLATE.md`）
3. `knowledge/ops/checkpoints.md` 最上加一行，层 = **买卖模型**，状态 = `已完成（仅回测）` 或 `待盯`
4. 对用户说话标明：**这是买卖模型 research，不是选股，不改 QMT。**

脚本放 `bt_research/wb_dd_*.py`，前缀 `wb_dd_` 以免和主电脑 Cursor 的 `bt_holdings_*` 撞文件。

---

## 不要做

- 改 `production_strategies/`、放宽 `t2_force`、改仓位
- 加密纸盘回撤（新加坡另一条线）
- 全市场因子 IC、重训 V25
- 每天发「回测已通过」长报告

做完票 1 先停，把 MAE/MFE 表发给用户。用户说继续再做票 2、票 3。
