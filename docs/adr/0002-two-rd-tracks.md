# Two R&D tracks inside Model Workshop (shared promotion gate)

Status: accepted

模型研发车间保留两套并行方案，且都不得干涉生产 Task Chain：

1. **Track A（Current Model Uplift）**：在现有 VM2.5 / `features_v2` 特征空间上做增量因子变换与 IC 筛选，再经晋升适配器做候选训练与可交易 OOS。入口：`rd_workshop/track_a_current_model_uplift.py`。
2. **Track B（RD-Agent Self-Dev）**：由 RD-Agent(Q) 独立假设并实现因子（可在 Qlib 环境），导出后归一化，再进入同一晋升适配器。入口：`rd_workshop/track_b_rdagent_self_dev.py`。

两套方案共享出口：`run_promotion_adapter.py` → Human Review → 可选 Promotion；禁止自动上线，禁止互相改对方任务链。

## Consequences

- Track A 更贴生产特征契约，迭代快，但探索半径受现有特征限制。
- Track B 探索半径大，可能挖出新结构，但需额外 RD-Agent/Qlib 环境，且必须过 AlphaPilot 可交易验收才有晋升意义。
- 对比生产模型时，报告中应标明 `track`，避免把两套实验混为同一候选血统。
