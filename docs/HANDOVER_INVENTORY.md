# AlphaPilot 项目移交清单 — 问题与优化方向

> **日期**: 2026-07-30
> **用途**: 与 WorkBuddy1（选股预测模型）、WorkBuddy2（量化交易模型）深入研讨
> **项目范围**: A股选股预测模型 + A股量化交易模型（含模拟盘与QMT实盘）

---

## 总览

```
AlphaPilot 系统架构
├── A股选股预测模型（WorkBuddy1）
│   ├── 05:00 主管线（alphapilot_pipeline_v3.py）
│   │   ├── 量价形态扫描 → VM2.5/ICIR评分 → 门控链 → Top50
│   │   └── 依赖: 55+维特征 + XGBoost集成 + ICIR因子加权
│   └── 研究车间（rd_workshop/）
│       ├── Track A: 现有特征空间挖增量因子
│       └── Track B: RD-Agent 自研因子
│
├── A股量化交易模型（WorkBuddy2）
│   ├── 09:35 实时扫描 + 排序（live_momentum_scanner）
│   ├── 09:36 信号生成（paper_trading_signals）
│   ├── 09:36+ 交易执行（trade_executor）
│   ├── 仓位管理（kelly_sizing + kelly_learner）
│   ├── 退出策略（Plan C / Plan E2 / adaptive_exit）
│   └── QMT实盘集成（qmt_model_plan_c.py）
│
└── 支撑系统
    ├── API服务器 + 前端页面
    ├── 数据管线（akshare / Wind MCP / 通达信）
    ├── 健康巡检 / 告警
    └── 部署脚本 / cron / 运维
```

---

## 第一部分：选股预测模型 — 问题与优化方向

### 1.1 当前选股管线架构（现状）

```
05:00 入口
  1. 美股隔夜因子收集（us_enhanced_collector + overnight_sentiment）
  2. 量价形态扫描（launch_patterns.py: 5000+ → 200-600 只）
  3. VM2.5评分（recommend.py → icir_scorer: 500 只）
  4. 软门控（soft_universe_gate: A臂启动+B臂回流）
  5. 资金门 → 板块门 → 市场环境 → S2加权
  6. LLM审核（DeepSeek: Top50 → 最终排序）
  7. 输出: daily_recommend.json（Top50 候选）
```

### 1.2 已知问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| P1 | **评分系统割裂：ICIR vs VM2.5 双轨未统一** | ⚠️ 高 | recommend.py 使用 ICIRScorer（因子线性加权）作为主线，VM25Scorer（XGBoost 集成）仅用于建特征。fusion_scorer.py 的权重（VM25=0.50, 资金=0.30, 板块=0.20）在管线中并未实际调用。两套评分输出不一致时缺少仲裁机制。 |
| P2 | **ICIR 因子权重老化** | ⚠️ 高 | icir_weights.json 有 regime 方案（normal/weak/severe），但 ICIR 因子 IC 会随时间衰减，当前无自动刷新周期，可能已偏离当前市场结构。 |
| P3 | **LLM 审核瓶颈** | ⚠️ 中 | DeepSeek 审核仅覆盖 Top50，5 线程并行，单次 10s 超时。若 API 限频或超时，会阻塞整体管线。硬编码 API key（alphapilot_pipeline_v3.py:19）。 |
| P4 | **特征工程备选数据源不稳定** | ⚠️ 中 | 55+ 维特征中有 11 个是基本面字段，但注释明确标注"占位，需要有效数据源"。fundamental_data.json 的可用性与完整性不确定。 |
| P5 | **icir_all_scores.json 生成时机不确定** | ⚠️ 中 | 09:35 scanner 消费 icir_all_scores，但它应该在 05:00 管线产出。若管线天亮前未完成，scanner 会读不到今日数据。 |
| P6 | **LLM 审核结果不可复现** | ⚠️ 低 | 同一 Top50 输入多次 LLM 审核得到不同结果，影响 ABC 测试的可比性。 |

### 1.3 优化方向（需研究）

| # | 方向 | 优先级 | 描述 |
|---|------|--------|------|
| R1 | **统一评分架构** | 高 | 确定最终评分方案：ICIR 线性加权 vs XGBoost 集成 vs 融合评分。建议 A/B 回测对比三者 OOS 表现后定稿一套。fusion_scorer 应实际接入管线（目前只接入了 paper_trading_signals）。 |
| R2 | **ICIR 因子自动刷新机制** | 高 | 建立因子 IC 的滚动跟踪（如 20 日滑动窗口），当因子 IC 连续衰减时自动调权或淘汰。可参考 `output/feedback/model_weights.json` 的 EMA 更新逻辑。 |
| R3 | **VM2.5 模型重训策略** | 高 | 当前 train_v25.py 支持 A/B 训练（base vs opt），但重训周期不明确。需要确定：多久重训一次？增量 vs 全量？OOS 验收标准是什么？ |
| R4 | **Track A 因子挖矿流程工单化** | 中 | track_a_current_model_uplift.py 每周六自动挖因子 → 候选训练 → OOS，但当前缺少可视化看板跟踪每次 OOS 的边际提升/衰减。建议与 WorkBuddy1 讨论：挖矿频率、因子池管理、晋升闸门标准。 |
| R5 | **Track B RD-Agent 激活** | 中 | Track B 当前仅运行环境检查（`--doctor`），RD-Agent 未实际安装（`pip install rdagent` 未执行）。需要讨论是否激活以及集成方案。 |
| R6 | **LLM 审核方案升级** | 中 | 考虑：a) 缓存同一股票当日新闻的 LLM 结果避免重复审核；b) LLM 结果作为辅助参考而非排序因子；c) 统一 prompt 模板 + 温度参数消除随机性。 |
| R7 | **特征工程补齐基本面数据** | 中 | 补齐 11 个基本面字段的数据源（EPS/ROE/营收增速等），评估基本面因子对 IC 的边际贡献。 |
| R8 | **05:00 管线执行稳定性** | 中 | 管线 13 个步骤顺序执行，单步失败会阻断后续。建议：a) 步级别 try-catch + 降级；b) 关键步骤超时兜底；c) 中间结果持久化支持断点续跑。 |
| R9 | **因子库系统化管理** | 低 | 当前因子分散在 features_v2.py、auto_factor_engine.py、icir_weights.json 三处。建议建立统一因子注册表（名称/定义/数据源/IC/生成日期）。 |

---

## 第二部分：量化交易模型 — 问题与优化方向

### 2.1 当前交易管线架构（现状）

```
09:25 — 集合竞价门控（pre_market_gate: 腾讯实时行情 → 5条规则）
09:35 — 全市场扫描（live_momentum_scanner: ICIR + 实时资金流双轨）
     → 盘中终选（morning_live_fund_select: 资金门 → Top2）
09:36 — 信号写入（paper_trading_signals: fusion_rerank → Kelly → 人工确认闸）
09:36+ — 执行（trade_executor: GapSoft C臂入场 → E2退出 → T+2强平）
14:30 — 尾盘狙击（S2 EOD: 单票最大80万）
14:45 — 收盘确认窗口（E2硬止损 + T+2强平确认）
16:15 — 反馈闭环（Kelly重训 + boost微调）
```

### 2.2 已知问题

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| Q1 | **退出策略三套不一致** | 🔴 致命 | paper_trading_signals.py 的 exit_policy 声明"Plan C"（阶梯-3%/5%，止盈+5%/10%），但 trade_executor.py 实际执行的是"Plan E2"（硬止损仅收盘确认+动态 Peel）。qmt_model_plan_c.py 又有自己一套 Plan C（同 Plan C 逻辑但 QMT 本地执行）。一个系统中同时存在三套互不相通的退出逻辑。 |
| Q2 | **QMT 实盘桥接不可用** | 🔴 致命 | qmt_bridge.py 文件缺失。文档约定的核心桥接模块不存在，QMT 实盘模式当前完全不可用。用户本地 QMT 运行 qmt_model_plan_c.py 时"读不到价格"。 |
| Q3 | **akshare 资金流数据源列漂移** | ⚠️ 高 | akshare.stock_fund_flow_individual 返回列数与 akshare 固期待不一致（13 vs 10列），导致 ValueError。已添加同花顺直抓降级，但速度慢~300只/秒。明日开盘需验证降级通路是否生效。 |
| Q4 | **GapSoft入场规则在集合竞价场景失效** | ⚠️ 中 | GapSoft 使用开盘价/昨收计算 gap，但集合竞价时昨收可能为 0（停牌后复牌首日）。pre_market_gate.py 对 gap 的计算与 trade_executor.py 的 GapSoft 入场规则使用不同的 gap 定义。 |
| Q5 | **Kelly 仓位文档与实际不一致** | ⚠️ 中 | kelly_sizing.py 默认 KELLY_ENABLE=1（Kelly开启），但 paper_trading_signals.py 的 protocol.sizing 写的是"默认等权（KELLY_ENABLE=0）"。用户看到的是相反声明。 |
| Q6 | **position_exposure 脆弱传递** | ⚠️ 中 | 多个模块（pipeline→scanner→picks→paper_trading→trade_executor）传递 position_exposure，曾有漏写导致 nuclear=0 的历史 bug。BYPASS 路径可能不完整。 |
| Q7 | **P3 交易前闸未被 cron 消费** | ⚠️ 中 | health_alarm.json 由 05:10 巡检写入，但 cron 行`09:36 paper_trading_signals.py`并无前置依赖检查。巡检虽然跑了，但若告警存在，需要 paper_trading 自己读并阻断。当日第一版代码已加此逻辑但尚未经生产验证。 |
| Q8 | **pre_market_gate.py 依赖腾讯实时行情** | ⚠️ 中 | 腾讯行情在 AI 负载高峰（09:25 恰好是 AI agent 密集调用时段）可能限频或超时。当前无备选行情源。 |
| Q9 | **fee/cost 模型未精确校准** | 低 | protocol.cost_rt 为固定值 0.0015，未区分买入/卖出的印花税、佣金、过户费。对高频/微利交易盈亏影响不可忽略。 |

### 2.3 优化方向（需研究）

| # | 方向 | 优先级 | 描述 |
|---|------|--------|------|
| S1 | **统一退出策略方案** | 高 | 必须决定生产环境使用哪一种退出方案。建议 A/B 回测 Plan C vs Plan E2 的历史表现差异。定稿后统一 paper_trading_signals、trade_executor、QMT 三处的 exit policy，消除歧义。Plan E2 当前使用收盘确认，而 Plan C 使用分钟级确认，两者时间颗粒度不同。 |
| S2 | **QMT 实盘集成方案** | 高 | 需要彻底解决两个问题：a) qmt_bridge.py 缺失（若走 MiniQMT 路线）；b) 用户本地 QMT 客户端 get_market_data_ex 返回空值。建议 WorkBuddy2 检查 QMT 的 API 版本兼容性文档，给出明确的调用方案。qmt_model_plan_c.py 应作为 QMT 内部策略运行还是 MiniQMT 远程调用？ |
| S3 | **Kelly 仓位优化** | 高 | 当前双架构（静态 Half-Kelly + 在线逻辑回归）的融合不够紧密。8 维特征到 entry_weight 的映射缺乏风险预算上限检查。还需研究：kelly_learner 的滚动窗口大小、学习率、特征工程是否需要扩展（如加入大盘环境特征）。 |
| S4 | **数据源容错架构升级** | 高 | 当前 akshare 单点故障已暴露。建议：a) 数据源优先级可配置（如 akshare > 同花顺 > Wind MCP > 腾讯 > 新浪）；b) 跨进程熔断状态持久化；c) 每个数据源有 grace period（如某源失败 3 次后当日不再重试）。 |
| S5 | **GapSoft 入场规则优化** | 中 | 研究：a) gap 阈值是否需要随市场环境调整（强市放宽、弱市收紧）；b) 集合竞价 gap + 开盘 1分钟 gap 双维度判断；c) 是否引入 VWAP 偏差作为辅助信号。 |
| S6 | **盘中调仓机制** | 中 | 当前仅在 09:36 和 14:30 两个时点产生交易信号。研究：a) 是否需要在 10:30/13:30 加盘中信号检查；b) 持仓浮盈/浮亏触发自动调仓（如浮盈>10%自动减仓）；c) 板块资金反转信号触发换仓。 |
| S7 | **cost_model 精确化** | 低 | 精确计算：买入佣金（万1~万2.5）+ 卖出佣金+印花税（千1）+ 过户费。建议走 Wind MCP 获取实际费率。并入 paper_trading.json 的 protocol.cost_model 输出。 |
| S8 | **QMT 策略代码工程化** | 低 | qmt_model_plan_c.py 目前是要用户手动粘贴到 QMT 编辑器的 200 行代码。建议提供版本管理方案：qmt 从 API 拉取最新策略代码，或通过部署脚本自动同步。 |

---

## 第三部分：跨领域系统性问题

### 3.1 P0-P4 防护体系执行状态

| 层级 | 内容 | 状态 | 说明 |
|------|------|------|------|
| P0 | **链路健康巡检** | ✅ 已部署 | data_health_check.py 05:10 cron，检查 pipeline 完成/daily_recommend/icir 数据。明早需验证首跑。 |
| P1 | **热修规范** | 📋 约定 | 改前读完整函数 → 三层测试(语法/运行/日志) → 备份命名规范。需要 WorkBuddy 确认执行。 |
| P2 | **数据源熔断与降级** | ⚠️ 部分 | akshare→同花顺抓到已做，腾讯/新浪备选已测试但未接入。跨进程熔断状态持久化未做。 |
| P3 | **交易前数据新鲜度闸门** | ✅ 已部署 | paper_trading_signals.py 检查 health_alarm + daily_recommend + picks 新鲜度。BYPASS_FRESHNESS_GATE=1 可跳过。未经验证。 |
| P4 | **盘中异常监测** | ⚠️ 部分 | 量比异动 10:00/10:30/14:00 已部署。但缺少持仓盘中异常偏离（如浮盈>10%无提示/连续下跌无响应）。 |

### 3.2 运维与工程债务

| # | 问题 | 说明 |
|---|------|------|
| O1 | **远程服务器路径硬编码** | 几乎所有 Python 文件硬编码 `/home/ubuntu/alphapilot`，本地开发环境无法直接运行调试。建议通过 `ALPHAPILOT_ROOT` 环境变量统一。 |
| O2 | **API Key 泄露风险** | alphapilot_pipeline_v3.py:19 和 api_server.py 中硬编码 DeepSeek API key（sk-7fed...）。建议迁移到环境变量。 |
| O3 | **JSON 文件截断风险** | 多个 load_json 函数（vm25_scorer._load_json、train_v25.load_json_safe）包含截断修复逻辑（rfind('},')），暗示 fund_flow_history.json 等大文件有部分写入风险。建议写入时使用原子操作（写.tmp→rename）。 |
| O4 | **cron 任务过多** | 当前 crontab 约 30+ 行，部分 job 在同一个时间片运行（如 09:35 有 3 个 job 几乎同时启动）。建议 cron 任务审计 + 依赖图化。 |
| O5 | **文档与实际不一致** | 多处文档与实际代码行为不一致：退出策略、Kelly enable、QMT 架构等。建议整体文档审计。 |
| O6 | **本地/远程代码不同步** | live_momentum_scanner.py 的本地与远程版本差异显著（远程有完整体 fallback）。需建立 CI 同步机制。 |

---

## 第四部分：研讨议程建议

### 4.1 与 WorkBuddy1（选股预测模型）讨论

```
1.  评分系统统一方案 — ICIR vs XGBoost vs 融合，A/B 回测对比
2.  VM2.5 模型重训策略 — 频率/范围/OOS验收标准
3.  ICIR 因子自动刷新机制 — 滚动 IC 跟踪与自动调权
4.  Track A 挖矿工单化 — 挖矿频率/因子池管理/晋升闸门
5.  Track B RD-Agent 是否激活 — 集成方案与资源评估
6.  LLM 审核方案 — 保留/升级/降级为辅助？
7.  特征工程补齐 — 基本面数据源补齐计划
8.  05:00 管线执行稳定性 — 步级别降级/超时/断点续跑
```

### 4.2 与 WorkBuddy2（量化交易模型）讨论

```
1.  退出策略统一 — Plan C vs Plan E2 的 A/B 回测对比，定稿一套
2.  QMT 集成方案 — MiniQMT vs 全量 QMT 策略？qmt_bridge.py 需求确认
3.  Kelly 仓位系统优化 — 双架构融合/风险预算/特征扩展
4.  数据源容错架构 — 优先级配置化/熔断持久化/备用源接入
5.  盘中调仓机制 — 是否需要增量信号+自动调仓？
6.  GapSoft 入场规则优化 — 市场自适应阈值
7.  cost_model 精确化 — 真实费率校准
8.  QMT 策略工程化 — 版本管理/自动部署方案
```

### 4.3 跨领域讨论

```
1.  P0-P4 防护体系推进 — P2 数据源熔断和 P4 异常监测的下一阶段
2.  工程债务清理 — 路径统一/API key 迁移/JSON 原子写入/cron 审计
3.  文档审计与对齐 — 确保文档反映真实代码行为
4.  本地与远程开发环境同步机制
```

---

## 附录：快速参考

### 关键文件索引

| 文件 | 行数 | 用途 | 负责人建议 |
|------|------|------|-----------|
| alphapilot_pipeline_v3.py | 329 | 05:00 主管线编排 | WorkBuddy1 |
| recommend.py | ~600 | 每日评分管线 | WorkBuddy1 |
| icir_scorer.py | ~200 | ICIR 因子加权评分 | WorkBuddy1 |
| vm25_scorer.py | ~400 | XGBoost 集成评分 | WorkBuddy1 |
| fusion_scorer.py | ~150 | 三路融合评分 | WorkBuddy1 |
| features_v2.py | ~500 | 55+维特征工程 | WorkBuddy1 |
| launch_patterns.py | ~400 | 量价形态扫描 | WorkBuddy1 |
| live_momentum_scanner.py | 1016 | 09:35 实时扫描 | WorkBuddy2 |
| paper_trading_signals.py | 667 | 信号生成+P3闸门 | WorkBuddy2 |
| trade_executor.py | 1687 | 模拟盘执行器 | WorkBuddy2 |
| pre_market_gate.py | ~300 | 集合竞价门控 | WorkBuddy2 |
| kelly_sizing.py | ~200 | Half-Kelly仓位 | WorkBuddy2 |
| kelly_learner.py | ~300 | 在线增量学习 | WorkBuddy2 |
| qmt_model_plan_c.py | ~200 | QMT策略脚本 | WorkBuddy2 |
| scripts/data_health_check.py | 104 | P0 健康巡检 | 共同 |
| rd_workshop/ | — | 研究车间 | WorkBuddy1 |

### 当前持仓状态（2026-07-30）

- 模拟盘: 本金 200 万，总资产 ~85 万，累计 +2.75%
- 当前持仓: 南山铝业(+6.9%) / 中孚实业(+4.83%) — 均已触 peel 等待
- QMT 实盘: 好想你 / 启明星辰 — 手动买入，QMT策略尚未执行交易

### 当前异常状态

- QMT 策略读不到价格（get_market_data_ex 返回空值）
- akshare 资金流列漂移（已加同花顺降级，待验证）
- P3 闸门和健康巡检 05:10 首次运行在明天（7/31）
