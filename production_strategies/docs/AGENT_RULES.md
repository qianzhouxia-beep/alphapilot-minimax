# Agent 修改规则 — 给 DeepSeek Harness / 任何外部 Agent

> **先读这份，再动任何生产代码。** 本文件是给非 Cursor Agent（DeepSeek Harness、WorkBuddy、其他 AI）的约束说明。

## 背景

2026-08-16 起，本项目所有**轨道 A + 轨道 B 落地生产代码**已统一归档到：

```
C:\Users\elvisq\Projects\alphapilot\production_strategies\
```

这是**唯一权威来源**。你交叉验证、审查、修改时，一律以本文件夹内文件为准。

## 你（Agent）必须遵守的规则

### 0. 选股模型 vs 买卖模型（必须分开讲）

- **选股模型在服务器**：名单、排名、融合权重。改选股只改服务器脚本 / `export_qmt_scores.py`，**不要改 QMT/通达信**。
- **买卖模型在 QMT/通达信**：P2、仓位、卖出。只有改买卖规则才动 `track_a/` / `track_b/`。
- 写 CHANGELOG、对用户说话时必须标明是哪一层。详见 `knowledge/strategies/selection_vs_execution.md`。
- 2026-08-28 已部署到交易端的是买卖模型里的 **IC 记账**（买入打分、卖出写 jsonl），不是改选股、也不是改 P2。

### 1. 只改归档文件夹，不改根目录副本

- 项目根目录的 `qmt_model_full_chain_v2.py`、`qmt_model_full_chain_template.py`、`tdx_full_chain.py`、
  `track_b_qmt_auction_sim.py`、`track_b_qmt_auction_live.py`、`track_b_tdx_auction_sim.py`、
  `export_qmt_scores.py` 都是**历史快照**，冻结。
- 你的所有修改只针对 `production_strategies/` 内的对应文件。

### 2. 每次修改必须写日志

- 追加到 `production_strategies/CHANGELOG.md`（在最新一条上方插入，倒序）。
- 按模板字段填写：修改人/Agent、涉及文件、版本变化、修改内容、原因/依据、验证、部署。
- 如果修改是你（外部 Agent）做的，修改人/Agent 一栏写你的名字，例如 `DeepSeek Harness`。

### 3. QMT 文件必须纯 ASCII

- 四个 QMT 策略文件（轨道 A 两个 + 轨道 B 两个）注释/字符串必须是 ASCII，否则 QMT 加密后报 `SyntaxError`。
- 校验命令：
  ```bash
  python -c "import ast,pathlib; p=pathlib.Path(r'文件路径'); b=p.read_bytes(); b.decode('ascii'); ast.parse(b.decode('ascii'))"
  ```
- TDX 文件允许 UTF-8 中文注释（TDX 平台直接运行明文）。

### 4. 改完要交付什么

完成修改后，你的交付物必须包含：

1. `production_strategies/` 内更新后的文件（你自己放回）。
2. `CHANGELOG.md` 追加记录。
3. 验证结果（ASCII / 语法 / 离线测试，含跑过的命令和输出）。
4. 明确说明：是否需要重新部署、部署到哪些交易端。

### 5. sim / live 一致性

- 轨道 A：`qmt_model_full_chain_v2.py`（模拟）与 `qmt_model_full_chain_template.py`（实盘模板）逻辑必须保持一致，差异只允许在 CONFIG 参数化。
- 轨道 B：`track_b_qmt_auction_sim.py`（模拟）与 `track_b_qmt_auction_live.py`（实盘模板）同理。
- 改动模拟盘逻辑时，必须同步改对应实盘模板。

## 文件清单（以归档文件夹为准）

| 轨道 | 文件 | 平台 | 备注 |
|------|------|------|------|
| A | `track_a/TrackA_track_a_qmt_full_chain_sim.py` | QMT 模拟盘 | v2.16，含 ABR 买入门 |
| A | `track_a/TrackA_track_a_qmt_full_chain_live.py` | QMT 实盘模板 | v2.16-tpl，CONFIG 参数化，含 ABR 买入门 |
| A | `track_a/TrackA_track_a_tdx_full_chain_sim.py` | TDX 模拟盘 | v2.14，含 ABR 买入门（盘口近似） |
| B | `track_b/TrackB_track_b_qmt_auction_sim.py` | QMT 模拟盘（第二账户） | v1.0，已修 F1/F2 |
| B | `track_b/TrackB_track_b_qmt_auction_live.py` | QMT 实盘模板 | v1.0-tpl，已修 F1 |
| B | `track_b/TrackB_track_b_tdx_auction_sim.py` | TDX 模拟盘 | v1.0，已修 F1/F2 |
| 服务器 | `server/export_qmt_scores.py` | 服务器 | `--fullpool` 06:30 导出 |
| 文档 | `docs/DUAL_TRACK_BRIEFING.md` | — | 双轨设计（已交叉验证） |
| 文档 | `docs/CODE_CROSSVALIDATION_BRIEFING.md` | — | 代码交叉验证任务书 |

## 服务器管线脚本（不在 production_strategies 内，但是活跃生产）

| 脚本 | 位置 | 规则 |
|------|------|------|
| `live_momentum_scanner.py` | 仓库根 / 服务器 `/home/ubuntu/alphapilot/` | **09:35 双路径**：见 `knowledge/strategies/0935_momentum_scanner.md` 与 `.cursor/rules/live-momentum-scanner.mdc`。修改后部署服务器，写全局知识库；**禁止**擅自删 Top1000 分支 |

> 命名约定（2026-08-16 起）：轨道 A 策略文件以 `TrackA_` 前缀、轨道 B 以 `TrackB_` 前缀，
> 一眼可辨。`mootdx_feed.py` 同时服务 A/B 轨道且被测试 import，保持原名。

## 历史已知问题（改代码前先核对）

- **B1**：拒单不写锁（`[REJECTED no lock written]` 后 continue）——6 文件已修复 ✅
- **B2**：卖单封顶 `can_use`——已修复 ✅
- **B3/B5**：T+1 保护（QMT `can_use<vol` / TDX `TodayBuyPosition`）✅
- **B4**：TDX 拒单判定 `int<0 或 ErrorId!=0`，不写锁 ✅
- **T+2 强平**：`T2_EXTEND_RATIO=0.95` 一次性延期 ✅
- **板块权限**：300/301、688/689、8/4/920 前缀判定，6 文件一致 ✅
- **F1**：板块聚合性能——`_sector_members_cache` + `SECTOR_AGG_MAX_MEMBERS=30` + gap 缓存时序保护 ✅
- **F2**：TDX 主动买边界——`bv`/`sv` 任一缺失返回 `None`（软跳过），不硬堵 ✅
- **F3**：拒单后 `sent_today` 阻止重试——**用户明确保留现状**，不要改 ⛔

## 与你的对接流程

1. 你要修改/审查 → 先读 `production_strategies/README.md` + `CHANGELOG.md`。
2. 改 → 更新 `production_strategies/` 内文件 + 写 `CHANGELOG.md`。
3. 交付 → 在报告中列出你改了哪几个文件、版本变化、验证结果、部署建议。

如有任何疑问，以 `production_strategies/README.md` 为准。
