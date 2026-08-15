# AlphaPilot 知识库总索引

> 本知识库是 AlphaPilot 的"大脑"——所有设计决策、验证结论、数据事实、策略规则都沉淀在这里，供 AI Agent 与人类随时检索。**结构稳定，内容持续更新。**

## 层级结构

| 层 | 目录 | 内容 | 更新频率 |
|---|---|---|---|
| L1 稳定知识 | `models/` `strategies/` `data_sources/` `signals/` `decisions/` | 人工确认的结论与规则 | 低频（周/月） |
| L2 动态知识 | `daily/` `market_env/` `reports/` | 每日自动沉淀 | 高频（日/周） |
| L3 数据 | `output/` `data/` | 机器可读的原始与派生数据 | 实时 |

## 内容索引

### 模型（models/）
- [`models/v25_106d.md`](./models/v25_106d.md) — 当前生产模型 V25 的 106 维档案：构成、训练标签、OOS 基线、晋升记录
- `models/index.md` — 全部候选/历史模型一览（待建）

### 策略（strategies/）
- [`strategies/buy_sell_rules.md`](./strategies/buy_sell_rules.md) — 买入/卖出/退出规则 + 回测依据（VWAP 回踩、T+2 收盘卖）
- `strategies/position_exposure.md` — 仓位阶梯与市场环境门控（待建）
- `strategies/index.md` — 全部策略一览（待建）
- 策略评估：`docs/朋友策略评估报告_2026-08-15.md`（抓龙头打板策略 vs AlphaPilot，含融合建议）
- 板块热度研究：`docs/板块热度时点研究_2026-08-15.md`（9:35/9:40/9:45 时点可靠性 + 板块热度稳定性）

### 数据源（data_sources/）
- [`data_sources/index.md`](./data_sources/index.md) — 每个数据源：路径、更新 cron、覆盖度、延迟、可靠性、风险

### 信号（signals/）
- [`signals/index.md`](./signals/index.md) — 已验证/已否决信号的结论卡汇总 + 置信度字段（自动回写）
- 每个信号一个文件，含：假设、回测口径、样本量、胜率、日期、结论

### 决策（decisions/）
- [`decisions/index.md`](./decisions/index.md) — 关键决策记录，含"为什么做了/为什么没做"
- 与 WorkBuddy 的协同共识也入这里

### 动态知识（自动生成）
- `daily/YYYY-MM-DD.md` — 每日决策单（09:45 自动生成）
- `market_env/YYYY-MM-DD.md` — 市场环境日记（09:45 自动生成）
- `reports/weekly_策略健康度.md` — 每周置信度报告（周六 10:00 自动生成）

## 维护规则

1. **Agent 干活前**：先在知识库找相关条目；找不到再动手，动手后补写。
2. **结论回写**：回测结论、决策、数据源变更必须回写对应档案。
3. **旧文档**：一次性讨论稿/同步稿保留在 `docs/`（只读档案），知识库只存"结论"不存"过程"。
4. **版本**：知识库与 `AGENTS.md` 同步演进；`docs/` 是流水，`knowledge/` 是水库。

## 与 docs/ 的关系

- `docs/`：一次性报告、讨论稿、历史档案（68+ 份，扁平堆放，只读）
- `knowledge/`：蒸馏后的稳定结论 + 自动沉淀的每日知识（本库）
- 迁移原则：docs 里的**结论**在知识库建档，**过程**留在 docs。

## 生成脚本

| 脚本 | 作用 | cron |
|---|---|---|
| `scripts/kb_daily_snapshot.py` | 生成每日决策单 + 市场环境日记 | 工作日 09:45 |
| `scripts/kb_bt_card.py` | 回测结论卡入库（--signal/--status/--n ...） | 手动 |
| `scripts/kb_confidence_report.py` | T+N 置信度统计回写信号档案 | 工作日 16:30 |
| `scripts/kb_weekly_report.py` | 每周策略健康度报告 | 周六 10:00 |
