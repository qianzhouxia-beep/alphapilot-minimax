# AlphaPilot 知识库总索引

> 本知识库是 AlphaPilot 的"大脑"——所有设计决策、验证结论、数据事实、策略规则都沉淀在这里，供 AI Agent 与人类随时检索。**结构稳定，内容持续更新。**

## 层级结构

| 层 | 目录 | 内容 | 更新频率 |
|---|---|---|---|
| L1 稳定知识 | `models/` `strategies/` `data_sources/` `signals/` `decisions/` | 人工确认的结论与规则 | 低频（周/月） |
| L2 动态知识 | `daily/` `market_env/` `reports/` `ops/` | 每日自动沉淀 + **Checkpoint 目录** | 高频（日/周） |
| L3 数据 | `output/` `data/` | 机器可读的原始与派生数据 | 实时 |

## 内容索引

### 模型（models/）
- [`models/v25_106d.md`](./models/v25_106d.md) — 当前生产模型 V25 的 106 维档案：构成、训练标签、OOS 基线、晋升记录
- `models/index.md` — 全部候选/历史模型一览（待建）

### 策略（strategies/）
- [`strategies/buy_sell_rules.md`](./strategies/buy_sell_rules.md) — 买入/卖出/退出规则 + 回测依据（VWAP 回踩、T+2 收盘卖）
- [`strategies/selection_vs_execution.md`](./strategies/selection_vs_execution.md) — **选股模型 vs 买卖模型**（服务器选股 / QMT·通达信买卖；必须分开讲）
- [`strategies/0935_momentum_scanner.md`](./strategies/0935_momentum_scanner.md) — **09:35 双路径**（≥100 池内重排 / &lt;100 Top1000 资金轨；弱市仍启用）
- **gene 重排不改（2026-09-10）**：19 个月双代理池 + 真实 30 天留出，25 变体无一个通过样本外 + family-wise 多重检验（最好 p≈0.50）→ **不部署**；**现行 gene 本身也未被样本外确认**（P2 OOS IC5 t=−2.7、真实留出 t 0.17），只是"保持现状 pending"。唯一影子候选 `GENE_plus_LOWACT6` 待真实 Top10 归档 ≥90~120 TD（`ops/shadows_registry.md` E 节）。inbox `2026-09-10-gene-redesign.md` + `decisions/2026-09-10-gene-redesign-proposal.md`
- **位置闸（2026-09-06 上线）**：服务器端硬过滤高位派发票 `up_low>0.5 & dist_hi<-0.05`，命中票 T+5 -7.33%(n=12) vs 未命中 +4.58%(n=23)；export 三路 + morning_live 09:35 双保险。决策 `decisions/index.md` 09-06 位置闸行 + inbox `2026-09-06-position-gate-live.md`。**补充渠道（&lt;100 → Top1000 资金轨）也经同一闸**（汇合点后的 recommendations 过滤）
- `strategies/position_exposure.md` — 仓位阶梯与市场环境门控（待建）
- `strategies/index.md` — 全部策略一览（待建）
- 策略评估：`docs/朋友策略评估报告_2026-08-15.md`（抓龙头打板策略 vs AlphaPilot，含融合建议）
- 板块热度研究：`docs/板块热度时点研究_2026-08-15.md`（9:35/9:40/9:45 时点可靠性 + 板块热度稳定性）
- 板块方向研究：`inbox/2026-08-25-sector-direction-fingerprint.md`（资金指纹相似匹配：动量更强，匹配法防守价值大）
- 板块方向生产接入：`inbox/2026-08-25-sector-fingerprint-production.md`（软加分+晨报上线；今日4只票完整漏斗）
- **风控红线**：`inbox/2026-08-25-st-hard-filter.md`（*ST威领事故：ST/*ST 全链路硬过滤，交易端+服务器 13 文件）
- **数据闸门闭环**：`MEMORY.md`「日常验证分工约定」+ `docs/LOG_2026-08-25.md`（08-24 筹码事故整改封口；FAIL-only WeCom）
- 情报层方案：`docs/情报层方案_2026-08-18.md`（OSINT 隔夜情报 + 异动归因，阶段 0/1/3 已落地）

### 数据源（data_sources/）
- [`data_sources/index.md`](./data_sources/index.md) — 每个数据源：路径、更新 cron、覆盖度、延迟、可靠性、风险（含 2026-08-15 / **08-22 回归** kline volume 单位 bug）。与 WorkBuddy 对齐的铁律：`docs/CURSOR_K线单位铁律_2026-08-22.md`
- [`data_sources/hithink.md`](./data_sources/hithink.md) — 同花顺官方 API（HiThink/Fuyao）：认证、缺口字段、REST/MCP、as-of 规则、生产不加排序
- [`data_sources/wind_investor_flow.md`](./data_sources/wind_investor_flow.md) — 万得全A四类净买入（央妈/量化/游资/散户），21:15 日度积累；主力 10/20/60 日累计可拉，无现成 30 日字段
- [`data_sources/2026-09-11-kline-fallback-sources.md`](./data_sources/2026-09-11-kline-fallback-sources.md) — **K 线多源兜底事实**：新浪不复权(主,带amount,volume=股) / 腾讯 gtimg(WAF 501 会封 IP, 688=股其余=手) / TDX 单源已加熔断；闸门已增查 `extra_factors`
- 入场口径审计（2026-09-11）：`inbox/2026-09-11-entry-timing-audit.md` — 61 组研究仅 G1 分支/WB 五分类/日度置信报告是 D+1 或坏价，**G1 晋升前必重算**；报告 `bt_research/entry_timing_audit_2026-09-11.md`
- [`inbox/2026-09-11-kline5m-backfill-baostock.md`](./inbox/2026-09-11-kline5m-backfill-baostock.md) — **5m 历史回补**：mootdx 仅 7 天 → 现存 34 天；用 **baostock**(不复权/volume=股/09:35起) 回补到 ≥6 个月，脚本 `bt_research/backfill_kline5m_baostock.py`（只加更早 bar、原子写、4 分片并行）
- [`inbox/2026-09-11-gap-bug-recheck.md`](./inbox/2026-09-11-gap-bug-recheck.md) — **五分类 gap 基数 bug 复核 + 三口径收口**：存档 `gap≡open(D+1)/close(D−1)−1`（124/127 证实，=跨两天收益）；真价 09:35 入场 → 全体 +1.50%→**+0.55%**、配对 t 9.93→5.66；**再叠加 plan_C 出场 → 全体 −0.21%、走高 t=0.59 不显著**（只剩"回避走低"t=−2.32）⇒ **G1 作否决尚存、作做多前提不成立**；`001232`次新真缺口 / `002667`ST设计内剔除
- [`inbox/2026-09-11-qmt-sim-not-running.md`](./inbox/2026-09-11-qmt-sim-not-running.md) — **今天 QMT 模拟盘没买**：①服务器模拟盘被情绪门控 freeze 拦截（涨停 10<20，设计内）；②**QMT 交易端未运行**（UA `QMT/2.2` 拉取 09-10=0 次、09-11 仅 3 次），非策略问题

### 信号（signals/）
- [`signals/index.md`](./signals/index.md) — 已验证/已否决信号的结论卡汇总 + 置信度字段（自动回写）
- 每个信号一个文件，含：假设、回测口径、样本量、胜率、日期、结论

### 决策（decisions/）
- [`decisions/index.md`](./decisions/index.md) — 关键决策记录，含"为什么做了/为什么没做"
- [`decisions/2026-09-11-code-flow-and-two-ends.md`](./decisions/2026-09-11-code-flow-and-two-ends.md) — **代码流向「仓库→服务器」+ 量化两端模型（选股端=服务器 / 交易端=本地 production_strategies）**；看 QMT 买卖逻辑查本地、不查服务器
- 与 WorkBuddy 的协同共识也入这里
- 2026-09-02：`vwap_weak_early` **二次确认**（第一次不卖）— CHANGELOG 2026-09-02 条
- 2026-09-01：轨道 A **关掉满仓踢最弱**（rotation off）+ **rank≤2 进 P2** — inbox `2026-09-01-rank-le2-p2-gate.md`
- 2026-08-28：**否决**网页融合排名前移到 QMT 顺序（池内重排 Top2 T+1 -0.44pp）— inbox `2026-08-28-fusion-web-rank-not-worth-forward.md`

### 运营目录（ops/）
- [`ops/checkpoints.md`](./ops/checkpoints.md) — **Checkpoint 时间点表**（什么时候做了哪一层的事、还要盯什么；新行追加在最上）
- [`ops/shadows_registry.md`](./ops/shadows_registry.md) — **影子/观察/监控注册表**（权威）：现在有哪些影子在跑、输出路径、积累状态、判定门槛、下次看；体检/新增影子先对照本表（2026-09-06 建）
- 新 WorkBuddy 入职：仓库根 [`docs/WORKBUDDY_HANDOFF.md`](../docs/WORKBUDDY_HANDOFF.md)（2026-09-02）
- Mac WorkBuddy 回撤研究任务：[`docs/WORKBUDDY_DRAWDOWN_RESEARCH.md`](../docs/WORKBUDDY_DRAWDOWN_RESEARCH.md)

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
