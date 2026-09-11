---
project: alphapilot
domain: architecture
title: 代码流向（仓库→服务器）+ 量化两端模型（选股端/交易端）
date: 2026-09-11
status: decision
tags: [architecture, workflow, qmt, repo, 选股端, 交易端]
---

# 代码流向（仓库→服务器）+ 量化两端模型

> 用户 2026-09-11 拍板。两条都是**长期有效**的架构约定，写进 `MEMORY.md`。

## 1. 代码流向：仓库 → 服务器（repo-first）

- **先改仓库，再从仓库推送到服务器**。不再"直接在服务器上改"。
- 用户原话：*"以后就按这个顺序：先仓库，再从仓库推送到服务器。以前新加坡服务器的流程就是这样的。"*
- ⇒ **仓库 = 代码之源**；服务器 = 部署目标。
- 背景：近期出现"服务器被 Windows Cursor / WorkBuddy 直接改、仓库落后"的情况，导致**读仓库会得出错误结论**（本会话"死代码"误报就是读了一份被改坏的仓库快照）。
- 边界：
  - **代码** → 仓库为准，push 后在服务器部署。
  - **数据新鲜度** → 仍以服务器（SSH 上海机 `data_readiness_gate.py`）为准，不以本地 stale 文件为准。

## 2. 量化两端模型（必须分清）

| 端 | 职责 | 代码位置 |
|---|---|---|
| **选股端** | 产生候选：05:00 管线 / 09:35 scanner / 09:36 导出 candidates | 服务器 `/home/ubuntu/alphapilot`（已镜像回仓库） |
| **交易端** | QMT/通达信执行买卖：买哪个 / 卖哪个 / 怎么卖 | **本地** `production_strategies/track_a` + `track_b`（+ `ptrade/`）的 live/sim |

- ⚠️ **看 QMT 买卖逻辑 → 查本地 `production_strategies/`，不要去服务器找。**
- 用户原话：*"如果你要看 QMT 的买卖代码，其实是要看这里的。应该去查看保存在本地端轨道 A 或轨道 B 的 QMT 实盘和模拟代码，而不是去服务器上找。"*

## 3. 由此产生的口径更正（重要）

- 服务器 `trade_executor.py` + `data/paper_trading.json` = **选股端自带的服务器纸面模拟**，**不是 QMT 交易端**。
- 因此此前"生产出场规则"的讨论中：
  - **交易端权威出场** = 本地 `production_strategies/track_a/TrackA_track_a_qmt_full_chain_{live,sim}.py`（Track B 同理）；
  - **实盘** = `..._live.py`（Track A 当前 **v2.38-tpl**）；**模拟** = `..._sim.py`（Track A 当前 **v2.45**）。实盘落后模拟若干版本属正常。
  - 服务器 `trade_executor.py` 的规则（Plan C 阶梯 + 峰值回撤 6%）**只是选股端纸面模拟**，不能当作"生产真实出场"。
- ⇒ 研究里要对比"生产出场"时，应取 **track A/B 的 live/sim** 口径，并**点名轨道 + live/sim + 版本**。

## 4. 部署分工（既有，重申）

- **交易端**：用户手动复制到 QMT python 目录 / TDX `PYPlugins\user`（规则 5）。
- **服务器端**：Agent 直接部署（scp / cron），自验并留痕。

## 关联

- `MEMORY.md`（"代码流向铁律 + 量化两端模型"）
- `production_strategies/README.md`、`.cursor/rules/production-strategies.mdc`
- `knowledge/decisions/2026-09-10-gene-redesign-proposal.md`（同类架构决策写法）
