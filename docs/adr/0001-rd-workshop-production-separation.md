# RD-Agent 作为独立模型研发车间，与生产任务链隔离

Status: accepted

要把 RD-Agent（及同类自动化 R&D）用于模型开发与提升，而不是替换选股/交易生产链路。我们决定：**Model R&D Workshop 与 Production 为各自独立的部门级上下文**——不得互相干涉对方 Task Chain；仅可互相提供只读 Data Support。Workshop 产出的 Candidate Model 必须先完成 Backtest Validation，再经 Human Review，并与当前 Production Model 对比后，才允许 Promotion 上线；禁止自动热切换或在生产 cron/信号/执行路径中嵌入研发循环。

## Considered Options

- **嵌入生产链路自动挖因子并上线** — 否决：污染交易链、难审计、易过拟合到错误评价口径。
- **RD-Agent 直接替换 Qlib/生产打分** — 否决：与 A 股可交易协议及资金门目标不对齐。
- **独立车间 + 数据互通 + 人工晋升（采纳）** — 保留自动化研发收益，上线权与生产稳定性留在 Production。

## Consequences

- 研发可独立迭代（含 RD-Agent），失败不影响当日选股与模拟盘。
- 需要明确的数据导出/导入约定与晋升检查清单；没有「一键同步模型」的隐式通道。
- 评价口径应在晋升门上对齐生产关心的回测（可交易 OOS 等），而不是只采用论文默认 IC/ARR。
- 晋升适配器：`rd_workshop/run_promotion_adapter.py` 将因子接到候选 `train_v25` + 可交易 OOS，报告止于 Human Review。
