# Context Map

AlphaPilot 拆成两个独立部门级上下文：生产交易与模型研发。二者不得互相改对方任务链；仅通过约定数据面互通。

## Contexts

- [Production](./docs/contexts/production/CONTEXT.md) — 日频选股、闸门、模拟盘/实盘执行与线上打分模型
- [Model R&D Workshop](./docs/contexts/rd-workshop/CONTEXT.md) — 离线因子/模型假设、实验、回测与候选模型产出；内含 **Track A（Current Model Uplift）** 与 **Track B（RD-Agent Self-Dev）**，共享晋升适配器出口。

## Relationships

- **Workshop → Production（只读数据支持）**：Workshop 可读生产侧落盘行情、资金流、特征旁路、历史推荐与回测基准快照；不得写入生产 cron、信号、订单、`paper_trading` 或线上 `models/` 生效文件。
- **Production → Workshop（只读数据支持）**：Production 可向 Workshop 导出匿名化/快照化的市场与标签数据、当前生产模型元数据与 OOS 基线指标；不得调用 Workshop 任务、不得在日内链路里触发挖因子。
- **Workshop → Production（晋升，非任务链耦合）**：仅经「回测验证 → 人工审核 → 与生产模型对比 → 明确上线决定」后，由人把候选制品安装进生产模型槽位。无自动热切换。工具入口：`rd_workshop/run_promotion_adapter.py`（只写 `rd_workshop/candidates/`）。
