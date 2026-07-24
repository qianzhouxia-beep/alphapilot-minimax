# Model R&D Workshop

离线模型与因子研发上下文（含 RD-Agent 等自动化 R&D）：假设、实现、回测与知识积累在此闭环。

## Language

**Candidate Model**:
研发车间产出、尚未成为 Production Model 的模型或特征配方。
_Avoid_: 生产模型, 线上模型

**Track A (Current Model Uplift)**:
在现有 Production Model 特征空间上挖掘增量因子并候选重训的研发轨道。
_Avoid_: 自研因子轨道, RD-Agent 轨道

**Track B (RD-Agent Self-Dev)**:
由 RD-Agent 等独立提出并实现因子、再导入晋升闸门的研发轨道。
_Avoid_: 现有模型微调轨道

**Backtest Validation**:
在约定评价口径下对 Candidate Model 的系统性回测验收；未通过则不得进入人工审核。
_Avoid_: 仅看训练集 AUC, 口头感觉

**Human Review**:
对照生产基线，由人对 Candidate Model 的回测与差异做上线与否的裁决。
_Avoid_: 全自动晋升, Agent 自决上线

**Data Support Import**:
研发从生产只读获取的数据与基线指标，用于实验；不构成对生产 Task Chain 的控制。
_Avoid_: 生产回调, 嵌入 cron

**Promotion Adapter**:
把任一 Track 的因子表接到候选 train_v25 与可交易 OOS、只写 candidates/ 的共享出口。
_Avoid_: 自动上线脚本
