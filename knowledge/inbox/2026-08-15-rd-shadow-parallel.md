---
project: alphapilot
domain: architecture
title: RD 晋升加速路径 A 落地：影子并行试运行（Shadow Top2）
date: 2026-08-15
status: decision
tags: [RD, 晋升加速, 影子, shadow, morning_live, 候选模型]
source_chat: RD 晋升加速
---

# RD 晋升加速：影子并行试运行落地

## 结论

用户选择加速路径 A（零风险影子并行）。已在生产 09:35 选股链路内实现**影子 Top2 旁路**：用 RD 候选模型（08-15 候选，116 维=106 生产+10 rd 因子）对**同一个 gated pool** 重打分，取候选 Top2，与生产 Top2 一并追加记录到 `output/shadow_top2_history.jsonl`。**只记录、不改生产 picks**；周一 09:35 起自动每日累积，1~2 周后可对比生产 vs 候选的真实盘中表现。

## 实现

- `morning_live_fund_select.py`：新增 `SHADOW_MODEL_DIR` 开关（默认关闭→零影响）与 `_shadow_rerank()` 旁路：
  - 生产 picks 已写入后才调用，绝不干扰主链路（try 包裹）
  - 同池同门控：对 `apply_money_flow_gate + research_sector_gate` 之后的同一 gated 池重打分
  - 用 `VM25Scorer` + `ALPHAPILOT_MODEL_DIR`/`ALPHAPILOT_EXTRA_FACTORS` 显式切到候选模型（已修复误加载生产 models 的 bug），用后恢复环境变量
  - 排序口径与生产一致：`money_flow_pass` 优先再按候选 score
  - 记录字段：date/asof/model_dir/n_gated/prod_picks(生产实际Top2)/shadow_picks(候选Top2)/expo
- `scripts/shadow_top2_history.py`：查看历史小工具
- `config/opening_scheme.env`：追加 `SHADOW_MODEL_DIR=.../track_a_current_model_20260815_020121/models`，cron 自动 source → 周一自动激活

## 验证

- 单测：候选模型经 VM25Scorer 加载 116 维 + 10 rd 因子正常打分（贵州茅台样例 ok）
- 端到端（模拟 cron source env + 跑 morning_live）：生产 Top2（乐心医疗/好想你）不变，候选 Top2（顺钠股份/星宸科技）正确记录，history 写入正常；测试后已恢复生产输出、清空 history 干净起点
- cron 确认：09:35 morning_live 行走 `opening_scheme.env`，影子将自动激活；paper_trading/feedback_loop 同 source 但无副作用

## 下一步

- 周一 08-17 起每日 09:35 自动累积 shadow Top2（生产 vs 候选）
- 1~2 周后用 `scripts/shadow_top2_history.py` 对比，若候选稳定优于生产，可人工评审走 PROMOTION_CHECKLIST 提前晋升
- 想切换候选模型时，只改 `config/opening_scheme.env` 的 `SHADOW_MODEL_DIR`
