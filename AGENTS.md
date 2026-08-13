# AGENTS.md — AlphaPilot Agent 入口

> 本文件是所有 AI Agent（Cursor / WorkBuddy / 任何编码代理）进入本仓库的引导。**先读这里，再干活。**

## 仓库是什么

AlphaPilot：A股量化选股 + 模拟盘/实盘执行 + 模型研发的完整体系。运行在上海服务器 `/home/ubuntu/alphapilot`，前端部署在 Zeabur（`alphapilot.api-tokenmaster.com`）。

## 第一站：知识库

**所有关于"系统怎么设计、为什么这么定、验证过什么、下一步做什么"的答案，都在 `knowledge/` 里。**

| 你要找什么 | 去这里 |
|---|---|
| 系统整体架构、模块职责 | `knowledge/INDEX.md` |
| 当前生产模型（106 维 V25） | `knowledge/models/v25_106d.md` |
| 交易策略规则与依据 | `knowledge/strategies/` |
| 每个数据源的覆盖度/延迟/可靠性 | `knowledge/data_sources/` |
| 已验证/已否决的信号与置信度 | `knowledge/signals/` |
| 关键决策与"为什么没改" | `knowledge/decisions/` |
| 每日选股记录（自动生成） | `knowledge/daily/` |
| 市场环境日记（自动生成） | `knowledge/market_env/` |
| 每周策略健康度报告（自动生成） | `knowledge/reports/` |

**规则：动手前先查知识库；结论后回写知识库。** 如果某个问题的答案不在知识库里，把它写进去。

## 关键上下文（快速版）

- **生产/研发分离**：生产 Task Chain（管线、闸门、模拟盘）与研发车间（`rd_workshop/`）互相只读，晋升必须人工。详见 `CONTEXT-MAP.md`。
- **管线**：05:00 跑 `alphapilot_pipeline_v3.py`，09:35 终选 → `output/daily_recommend.json` + `output/score_top10.json`。
- **数据**：K线 `data/kline_cache/kline_all.parquet`、资金流 `data/fund_flow_history.json`、筹码 `data/chip_data_all.json`。
- **模型**：生产 = V25 **106 维**（82 base + 8 derived + 6 chip + 10 tech），三模型集成 `models/v25_opt_ensemble_{1,2,3}.ubj`。注意"116 维"是 fd1 实验维度，**不是**生产口径。
- **执行**：模拟盘 Top2 × position_exposure，VWAP 回踩低位买入，T+2 收盘卖（细节见 `knowledge/strategies/`）。

## 工作协议

1. 修改前端 → 改 `frontend/`，git push 触发 Zeabur 自动部署。
2. 修改后端 → 服务器 `/home/ubuntu/alphapilot/{api_server,run_server}.py`，`sudo systemctl restart alphapilot-api`。
3. 回测/实验 → `rd_workshop/` 或 `bt_research/`，禁止直接碰生产 cron。
4. 结论沉淀 → 写 `knowledge/`，并同步更新 `knowledge/INDEX.md`。
5. 与 WorkBuddy 协同 → 同步稿入 `knowledge/decisions/`。

## 目录速查

```
alphapilot_pipeline_v3.py      # 05:00 主管线
recommend.py                   # 模型打分
vm25_scorer.py                 # VM2.5 推理（106 维）
scripts/build_score_top10.py   # 09:38 三路融合 Top10
scripts/archive_daily_picks.py # 09:40 归档每日选股
scripts/accumulate_top2_t1t5.py# 16:25 T+N 置信度数据
morning_live_fund_select.py    # 09:35 终选
trade_executor.py              # 模拟盘执行
knowledge/                     # ← 本知识库
```
