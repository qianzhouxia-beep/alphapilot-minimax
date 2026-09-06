---
project: alphapilot
domain: strategy
title: RD 自动调权（feedback_auto_tune）修复：空转 → 真正影响 09:35 资金轨排序
date: 2026-08-29
status: conclusion
tags: [RD, 自动调权, IC, scanner, 修复]
source_chat: RD自我提升调整修复
---

# RD 自动调权（feedback_auto_tune）修复：空转 → 真正影响 09:35 资金轨排序

## 结论（2-3 句）

**空转根因**：`feedback_auto_tune.py` 一直在跑但从未调过一次权重——三处设计错位。**已全部修复并部署服务器**（2026-08-29）。修复后：因子 IC 有真实值、调权窗口规则可触发、`W_ICIR/W_MOMENTUM` 真正进入 scanner 排序。

## 空转的三个根因（原来为什么没用）

1. **因子字段对不上**：脚本读 `momentum_score`/`sector_heat_hit`/`pipeline_hit`，`daily_recommend.json` 实际字段是 `_live_momentum_z`/`_pipeline_z`/`ml_score`（主路径）或 `_icir_z`/`_momentum_z`（资金轨）→ 三因子 IC 恒 0。
2. **调的参数没人用**：脚本调 `W_HEAT`/`W_PIPELINE`/`SURGE_ARM_B_MULT`，scanner 只消费 `W_ICIR`/`W_MOMENTUM`（资金轨 final=icir_z×W_ICIR+momentum_z×W_MOMENTUM）→ 即使调了也改变不了选股。
3. **scanner 不读调权输出**：`W_ICIR/W_MOMENTUM` 硬编码 0.50，`feedback_params.env` 无人消费。另外调权门槛「连续 5 天同向」太苛刻，基本不触发。

## 修复内容（2026-08-29 已部署服务器）

1. **字段映射自适应**：主路径 `ml_score`/`_live_momentum_z`/`_pipeline_z`；资金轨 `_icir_z`/`_momentum_z`（scanner 落盘新增）；HEAT=热度命中（`hot_sector_prefer`/`auction_sector_hit`/`wind_prefer_hit` 任一非空）。
2. **调权规则**：近 10 天窗口均值 |IC|≥0.03 且同向占比 ≥60%、≥5 个有效日才调，STEP 0.05，范围 [0.10, 0.80]。无效日不再写假 0。
3. **只调真实消费参数**：`TUNE_PARAMS = {ICIR: W_ICIR, MOMENTUM: W_MOMENTUM}`。
4. **scanner 接线**：读 `config/feedback_params.env`（16:15 写 → 09:35 读；文件缺失回退 0.50，行为不变）。

## 验证

- 本地：auto_tune 上调/下调/样本不足三场景单元测试全过；真实数据四因子 IC 非 None。
- 服务器：08-28 资金轨 rec 模拟 `_icir_z`/`_momentum_z` 后 ICIR/MOMENTUM IC 非 None、调权可触发、语法 OK。

## 边界（还没覆盖的）

- **主路径**（池≥100）排序权重 `0.6/0.4`（pipeline_z × 0.6 + momentum_z × 0.4）硬编码，不参与 RD 调权。RD 调权当前只作用**池<100 资金轨**路径。
- `W_HEAT/W_PIPELINE/SURGE_ARM_B_MULT` 保留固定值写 env 但无消费点（历史遗留死参数，本次不引入新消费）。
- 需要工作日真实 09:35 落盘 + 16:15 调权跑一周以上，验证首次实际调权。

## 关联

- `production_strategies/CHANGELOG.md`（2026-08-29 RD 自动调权修复）
- `knowledge/ops/checkpoints.md`（RD 接线已完成行）
- `knowledge/inbox/2026-08-28-two-ic-loops-and-live-ledgers.md`（两套 IC 对照）

