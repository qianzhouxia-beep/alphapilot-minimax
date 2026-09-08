# Research Factory：Walk-Forward OOS + Paper–Live 对齐（隔离实验，验证后再替换）

Status: accepted

## Context

生产 Task Chain 与 Model R&D Workshop 已隔离（ADR-0001/0002）。当前痛点是：纸面/回测报告好看，实盘或纸面成交不尽如人意。目标只有一个——**能赚钱**，且 **报告口径与实际操作一致**。

## Decision

1. **新增 Track C / Research Factory**，代码与产物只落在 `rd_workshop/research_factory/`，**不得**写入生产 `models/`、不得改 cron、不得改 `trade_executor` / `recommend` / 管线，**不得自动推送或部署**。
2. 验收北星：**同一交易规则快照下，Rolling Walk-Forward OOS 净收益曲线须与同期纸面实盘可归因对齐**；未过线不得晋升。
3. 交易规则以 **显式快照** `trade_rules_snapshot.json` 进入实验室（从生产常量拷贝并注明版本）。实验室仿真器只读该快照；生产代码保持不动。验证通过后，再人工决定是否把实验室实现 **替换** 进生产（另开晋升流程）。
4. Walk-Forward 协议与纸面–实盘对齐门槛写在 `rd_workshop/research_factory/PROTOCOL.md`；晋升前仍须走 `PROMOTION_CHECKLIST.md`，并增加「parity 报告 PASS」勾选。

## Consequences

- 研发可严格做 OOS / 对齐实验，失败不影响当日选股与模拟盘。
- 短期会有「双轨规则」：实验室快照 vs 生产源码；必须记录 `snapshot_version`，避免 silently drift。
- 真正替换生产仿真路径属于后续 Promotion，不在本 ADR 自动执行范围内。
