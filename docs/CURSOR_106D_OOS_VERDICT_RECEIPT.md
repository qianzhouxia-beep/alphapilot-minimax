# 106 维官方 OOS 基线验证记录（Cursor 侧落地回执）

日期: 2026-08-07
关联: `docs/CURSOR_106D_OOS_VERDICT.md`（WorkBuddy → Cursor 定论）

## 验证结论：WorkBuddy 结果可复现 ✅

在服务器用官方基线 `wb_106d_walkforward.py`（106 维 / 1 日标签 / V3 侧车 / chip 4906）重跑，独立复现（2026-08-07 完成）：

| 指标 | WorkBuddy FINAL JSON | Cursor 复现 | 差异 |
|------|---------------------|------------|------|
| W1 AUC | 0.6996 | **0.6995** | 0.0001 |
| W1 RankIC | 0.2241 | **0.2241** | 0 |
| W1 Top5 | 0.305 | **0.306** | 0.001 |
| W1 Top10 | 0.268 | **0.270** | 0.002 |
| W1 训练样本 | 1,338,277 | **1,338,277** | 0 |
| W2 AUC | 0.6310 | **0.6301** | 0.0009 |
| W2 RankIC | 0.1618 | **0.1606** | 0.0012 |
| W2 Top5 | 0.275 | **0.265** | 0.010 |
| W2 训练样本 | 1,647,279 | **1,647,279** | 0 |

→ 评估管线、数据、口径三者一致，**生产 106 维模型 OOS 有效成立**。
结果文件：`output/wb_106d_walkforward_20260807.json`

## Cursor 已落地清单

### P0-1 评估基线切换 ✅
- 官方基线定为 `bt_research/wb_106d_walkforward.py`（106 维 / FORWARD_DAYS=1）
- 服务器旧 67 维 `v25_oos_walkforward.py` → 归档为 `.disabled_20260807`（FORWARD_DAYS=5 口径错配，弃用）
- 服务器写 `OOS_BASELINE_README.md` 说明基线
- 脚本新增 `--forward-days` / `--out` 参数，支持 3 日标签对照

### P0-2 补数据缺口 ✅
| 数据 | 修复前 | 修复后 | 手段 |
|------|--------|--------|------|
| event 业绩预告 | 213 只 (4.3%) | **4188 只 (84%)** | `pull_margin_event_data.py` 改为合并 7 个报告期(新→旧) |
| lhb 龙虎榜 | 2201 只 (44%) | **3067 只 (61%)** | `pull_lhb_history.py` 支持 `--days 250` 一年回填 |
| margin 两融 | — | **4093 只 (80%)** | 同脚本顺带拉全 |

- 新增 cron：04:40 `pull_margin_event_data.py`、04:45 `pull_lhb_history.py --days 250`
- 修复版脚本已同步服务器 + 本地 `data/`

### P0-3 SSH 稳定性 ✅（根因纠正）
- 实测握手 10/10 成功 (0.32s) → **不是服务器 SSH 问题**
- 真实根因：旧脚本 `exec_command(timeout=X)` 对长任务（大文件/评估）误超时；命令实际都成功
- 落地 `bt_research/srv_ssh.py` 稳健封装（run/run_bg/download/upload，以远端 exit_code 为准）

### P1 ✅（部分）
- 资金流深度 134→250+：东财硬顶 120 天实测确认；新浪源可 250-500 天（相关 0.85-0.97 但量级偏移）→ 方案落地 `docs/P1_FUND_FLOW_DEPTH_PLAN.md`（分层映射拼接，待模型评估后执行）
- 标签对照：脚本已支持 `--forward-days 3`
- 健康度口径：审计确认生产**无**「模型状态感知/降权」逻辑（`fusion_scorer.py` 是交易 PnL IC 反馈，合理保留）；无需修改

### verify 生产 106 维一致性 ✅
- `v25_meta.json`：base 82 + derived 8 + chip 6 + tech 10 = 106，forward_days=1，threshold=0.03
- 评估脚本动态特征 82 = 生产 base_count 82
- `vm25_scorer.py` 推理 `feature_names` 取自模型文件（106 维），无 RD 注入不一致

## 状态
- [x] P0-1 基线切换
- [x] P0-2 数据补缺 + cron
- [x] P0-3 SSH 根因 + 工具
- [x] P1 方案落地
- [x] 106 维官方基线验证复现（W1/W2 全对齐）
- [ ] 3 日标签对照跑（`--forward-days 3`）
- [ ] 资金流深度拼接实施（待 P1 文档方案过审）
- [ ] 分市场建模 / 月度滚动重训 / QMT 盘中信号（P2）
