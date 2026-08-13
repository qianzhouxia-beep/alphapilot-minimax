# 数据源档案

> 每个数据源的路径、更新 cron、覆盖度、延迟、可靠性。用于 Agent 判断"这个数据可用吗"。

## K 线

| 项 | 说明 |
|---|---|
| 路径 | `data/kline_cache/kline_all.parquet`（软链根目录 `kline_all.parquet`） |
| 覆盖 | 全 A ~5000 只，2025-01 起 |
| 更新 | 工作日 15:15 `fix_kline_server.py` + 16:15 `sync_kline_root.py` |
| 增量 | `cache_kline.py update`（⚠️ 2026-08-13 曾 pyarrow 类型错误失败，未影响线上） |
| 5分钟线 | `data/kline5m/{code}.parquet`（48 根/天），16:20 `build_kline5m.py` |
| 可靠性 | ✅ 高，多次审计 |

## 资金流

| 项 | 说明 |
|---|---|
| 日度历史 | `data/fund_flow_history.json`（~5008 只 × 多日） |
| 构建 | 工作日 21:00 `build_fund_flow_history.py`（从 04:52 移到 21:00，因为 tdxhub 当天数据更新晚） |
| 盘中资金 | `output/institutional_watch.json` + `institutional_watch_history.jsonl`（每 3 分钟 `institutional_watch.py --loop --interval 180`） |
| 资金强度 | `output/fund_strength.json`（04:30 重建 `fund_strength.py --rebuild`） |
| 可靠性 | ✅ 日度稳定；盘中历史仅积累数天（2026-08-05 起），资金背离信号需 3-4 周 |

## 筹码

| 项 | 说明 |
|---|---|
| 路径 | `data/chip_data_all.json` |
| 覆盖 | 4906~4992 只 |
| 更新 | **由本地 WorkBuddy 拉取上传**（`upload-chip-data` API） |
| 可靠性 | ⚠️ 依赖人工/WorkBuddy 本地动作，非全自动。refresh 管线标注"chip 需通过 WorkBuddy 上传" |

## 板块/行业

| 项 | 说明 |
|---|---|
| 行业映射 | `data/stock_industry_map.json` |
| 概念映射 | `data/stock_concept_map.json` |
| 板块流 | `data/sector_flow_*.json`、`data/concept_flow_*.json` |
| 板块热度 | `output/hot_sector_bypass_pool.json`、`output/call_auction_sector_heat.json`（09:25 竞价） |
| 更新 | `scripts/refresh_sector_board_flows.py` 等 |

## 财务/事件/两融

| 项 | 说明 |
|---|---|
| 基本面 | `scripts/build_fundamental_data.py`（16:50） |
| 两融 | `data/margin_data.json`（04:40 `pull_margin_event_data.py`） |
| 龙虎榜 | `scripts/pull_lhb_history.py --days 250`（04:45） |
| 事件 | 同上 margin_event |

## 行情快照（选股产物）

| 产物 | 路径 | 生成 |
|---|---|---|
| 终选 | `output/morning_live_picks.json` | 09:35 |
| 三路融合 Top10 | `output/score_top10.json` | 09:38 |
| 每日归档 | `output/daily_picks_archive/YYYY-MM-DD/{top2,top10_gated,top10_ungated}.json` | 09:40 |
| T+N 统计 | `output/top2_t1t5.json` + `report.md` | 16:25 |
| 市场环境 | `output/market_env_snapshot.json` | 05:00 管线 |
| 资金强度 | `output/fund_strength.json` | 04:30 |

## 已知数据风险清单

1. 🔴 **筹码依赖 WorkBuddy 本地上传**，非全自动 → 缺筹码时特征降维（106→22），模型退化。
2. 🟡 **institutional_watch_history 深度不足**（2~3 天）→ 资金背离信号不可回测，需积累至 09 月初。
3. 🟡 **cache_kline.py update 有 pyarrow 类型 bug**（2026-08-13 失败）→ 增量更新需修。
4. 🟢 K线/资金流日度覆盖已审计达标（`freshness_coverage_check.py`、`daily_coverage_check.py`）。
5. 🟢 每日 17:35 `scripts/data_accumulation_check.py` 巡检数据积累。
