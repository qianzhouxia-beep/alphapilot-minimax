# 数据源档案

> 每个数据源的路径、更新 cron、覆盖度、延迟、可靠性。用于 Agent 判断"这个数据可用吗"。

## K 线

| 项 | 说明 |
|---|---|
| 路径 | `data/kline_cache/kline_all.parquet`（权威）。根目录 `kline_all.parquet` **是独立副本不是软链**，修 cache 后必须覆盖根文件 |
| 覆盖 | 全 A ~5000 只，2025-01 起 |
| 更新 | 工作日 15:15 **仓库根目录** `fix_kline_server.py`（cron 不跑 `bt_research/` 里那份）+ 16:15 `sync_kline_root.py` |
| 增量 | `cache_kline.py update`（⚠️ 2026-08-13 曾 pyarrow 类型错误失败，未影响线上） |
| 5分钟线 | `data/kline5m/{code}.parquet`（48 根/天），16:20 `build_kline5m.py` |
| 可靠性 | ✅ 高，多次审计。⚠️ volume 单位踩坑两次：08-15、**08-22 回归**（见下） |

> ⚠️ **volume 单位事实（口径=股）**：`amount/(volume*close)` 中位数 ≈1 为股，≈100 为手。通达信 mootdx `vol`/`volume` 是**手**，写入前必须按行自适应 ×100。
>
> - **2026-08-15**：历史 parquet 已按行 ×100；脚本补丁写成 `if volume 列不存在: vol*100`。mootdx **同时返回 volume 列（手）**，该分支是死代码。
> - **2026-08-22 查清回归**：08-17 起 cron 仍跑 08-15 上传的带锁脚本，但 ×100 从未执行；DAYS=20 keep=last 从 07-21 起重写成手（600519 08-21 修复前 ratio=100.42）。已再修：119,755 行 ×100；**按 ratio 转单位（不看列名）**；写后校验；同步根目录独立副本；`rd_health_check.py` 盯 ratio 与 fill_rate=0。
>
> 生产 `data_fetcher` 走 Sina 源（volume=股，不受影响）。**新写入 K 线的代码必须保持 volume=股。**
>
> **备用源 westock（2026-09-11 起）**：可批量拉日线（不复权），但 **volume 单位按板块不统一——688=股、其余=手**（`amount/(vol×close)`：688≈1，其余≈99.5）。详见 [`westock.md`](./westock.md)。
> **事故档案**：09-10 全量缺口（TDX 服务端中断 0/4991）与恢复 = [`2026-09-11-kline-0910-recovery.md`](./2026-09-11-kline-0910-recovery.md)。

## 资金流

| 项 | 说明 |
|---|---|
| 日度历史 | `data/fund_flow_history.json`（~5008 只 × 多日，主力单口径） |
| 构建 | 工作日 21:00 `build_fund_flow_history.py`（从 04:52 移到 21:00，因为 tdxhub 当天数据更新晚） |
| 分层日度（金额，已暂停） | `data/layered_flow_daily/`（东财超大/大/中/小）。`pull_layered_daily.py` cron 已撤。**不要**拿来当机构/量化 |
| 万得全A 四类净买入 | `data/wind_investor_flow_daily/YYYY-MM-DD.json`（881001.WI：央妈/量化/游资/散户）。工作日 21:15 `scripts/pull_wind_investor_daily.py`。档案：[`wind_investor_flow.md`](./wind_investor_flow.md) |
| 盘中资金 | `output/institutional_watch.json` + `institutional_watch_history.jsonl`（每 3 分钟 `institutional_watch.py --loop --interval 180`） |
| 资金强度 | `output/fund_strength.json`（04:30 重建 `fund_strength.py --rebuild`） |
| 09:35 双热 shadow | `output/market_flow_condition_shadow.jsonl`（`market_flow_condition_shadow.py`，5日全A主力环境×池内双热，只读） |
| 可靠性 | ✅ 日度稳定；盘中历史仅积累数天（2026-08-05 起），资金背离信号需 3-4 周 |

## 筹码

| 项 | 说明 |
|---|---|
| 路径 | `data/chip_data_all.json` |
| 覆盖 | 4906~4992 只 |
| 更新 | **由本地 WorkBuddy 拉取上传**（`upload-chip-data` API；批次文件 `_chip_batch_{NN}_{date}.json` → `_upload_chip_{date}.py` 合并） |
| 可靠性 | ⚠️ 依赖人工/WorkBuddy 本地动作，非全自动。refresh 管线标注"chip 需通过 WorkBuddy 上传" |
| 事故教训（08-24） | 批次缺 18/19（400 只）照常上传 → 1192 只保留服务器旧数据停 08-21。生产链路是 WorkBuddy 上传的**真实 CYQ**，**不是** `pull_chip_from_kline.py`（推演口径，勿用其覆盖） |
| 防线 | 上传前 `python3 scripts/check_chip_batches.py --date $(date +%F)`（缺批次/覆盖<4850/日期不符→禁止上传）；服务器 18:15 `daily_coverage_check` 复查；04:50 `data_readiness_gate` chip 最新日覆盖率 ≥95% 才 ready |

## 板块/行业

| 项 | 说明 |
|---|---|
| 行业映射 | `data/stock_industry_map.json` |
| 概念映射 | `data/stock_concept_map.json` |
| 板块流 | `data/sector_flow_*.json`、`data/concept_flow_*.json` |
| 板块热度 | `output/hot_sector_bypass_pool.json`、`output/call_auction_sector_heat.json`（09:25 竞价） |
| 更新 | `scripts/refresh_sector_board_flows.py` 等 |

## 同花顺官方（hithink / fuyao，2026-08-22 起）

完整用法（接口、MCP、as-of、Key）：[`hithink.md`](./hithink.md)

| 项 | 说明 |
|---|---|
| 用途 | 补缺口：涨停/跌停/炸板、连板、热股、龙虎榜、竞价、异动。不替换 Sina/腾讯/mootdx |
| 脚本 | `scripts/hithink_overlay.py`（15:40 归档）；`hithink_p2_side.py`（09:35 标注，**默认不改分**） |
| 产出 | `output/hithink_overlay.json` + `output/hithink_archive/YYYY-MM-DD.json` |
| cron | 工作日 15:40 |
| 认证 | `config/hithink_api_key.conf`（服务器 0600）或 `HITHINK_FINANCE_API_KEY`；本机 `~/.hithink_finance_api_key` |
| 对话取数 | Cursor MCP `user-fuyao-a-share` / `user-fuyao-a-share-index` / `user-fuyao-fund` / `user-fuyao-meta` |
| 选股 | ❌ 2026-08-22 as-of 回测：T-1 涨停/热股/龙虎榜 **不加进 P2 排序**。见 `knowledge/signals/hithink_p2_t1.md` |
| 可靠性 | ✅ REST 可用；收盘价与新浪一致。⚠️ 无分钟 K / L2 / 期货 / 外盘；竞价无历史；热股 `day`=24h 榜；日历返回 `YYYYMMDD` |

## 财务/事件/两融

| 项 | 说明 |
|---|---|
| 基本面 | `scripts/build_fundamental_data.py`（16:50） |
| 两融 | `data/margin_data.json`（04:40 `pull_margin_event_data.py`） |
| 龙虎榜 | `scripts/pull_lhb_history.py --days 250`（04:45） |
| 事件 | 同上 margin_event |

## 逐笔成交 / 主动买占比（Level-2 风格，免费）

| 项 | 说明 |
|---|---|
| 数据源 | **mootdx**（通达信协议开源客户端，免费，无需 L2 权限）`transaction()`=当日逐笔 / `transactions()`=历史逐笔（分页） |
| 实时 feed | `production_strategies/track_b/mootdx_feed.py`（独立进程，交易日 09:15-15:00，每 20s 轮询）→ `C:\alphapilot\l2_feed\{date}.json`，每条含 `abr`（当日累计主动买/买卖总量）、`buy_vol`、`sell_vol`、`ts`、`n` |
| 消费方 | Track B 资金门 ABR + **Track A v2.13 ABR 买入门**（QMT） |
| 历史逐笔 | `fetch_tick_abr.py`（track_a）按 5 分钟桶聚合 → `D:\alphapilot\data\tick_abr\{sym}_{date}.json`（回测用，165 文件） |
| buyorsell 语义 | 0=主动买 / 1=主动卖 / 2=中性 / 8=竞价撮合（2/8 不计入 ABR） |
| 5m K 线补数 | `backfill_k5m_aug.py`（track_a）：`bars(frequency=0)`=5 分钟，`frequency=5` 是周线（坑）→ `D:\alphapilot\data\kline5m_full_backfill\` |
| 可靠性 | ✅ 交易日实时可用；非交易时段无逐笔（feed 保留最后快照）。⚠️ 主动买卖方向为近似（成交价 vs 买卖一档），非交易所官方 L2 |

## 行情快照（选股产物）

| 产物 | 路径 | 生成 |
|---|---|---|
| 终选 | `output/morning_live_picks.json` | 09:35 |
| 三路融合 Top10 | `output/score_top10.json` | 09:38 |
| 每日归档 | `output/daily_picks_archive/YYYY-MM-DD/{top2,top10_gated,top10_ungated}.json` | 09:40 |
| T+N 统计 | `output/top2_t1t5.json` + `report.md` | 16:25 |
| 市场环境 | `output/market_env_snapshot.json` | 05:00 管线 |
| 资金强度 | `output/fund_strength.json` | 04:30 |
| 竞价快照归档 | `output/pre_market_archive/YYYY-MM-DD.json`（**09-07 起每日**；竞价量影子[S-CALL]的历史源头） | 09:25:55 `pre_market_gate.py` |

## 已知数据风险清单

1. 🔴 **筹码依赖 WorkBuddy 本地上传**，非全自动 → 缺筹码时特征降维（106→22），模型退化。
2. 🟡 **institutional_watch_history 深度不足**（2~3 天）→ 资金背离信号不可回测，需积累至 09 月初。
3. 🟡 **cache_kline.py update 有 pyarrow 类型 bug**（2026-08-13 失败）→ 增量更新需修。
4. 🟢 K线/资金流日度覆盖已审计达标（`freshness_coverage_check.py`、`daily_coverage_check.py`）。
5. 🟢 每日 17:35 `scripts/data_accumulation_check.py` 巡检数据积累。
6. ⚠️ **fix_kline volume 单位 bug 修过两次**（08-15 / **08-22 回归**）：cron 必须跑带 ratio 自适应 ×100 的**根目录** `fix_kline_server.py`；根 `kline_all.parquet` 是独立副本。健康检查 `rd_workshop/rd_health_check.py` 盯末日期 ratio≥20 与影子 fill_rate=0。
7. 🟢 **同花顺官方 API 已接入**（08-22）：补涨停/热股/龙虎榜/竞价缺口；Key 不进 git；**不进 09:35 打分**。档案 `knowledge/data_sources/hithink.md`。
8. 🟢 **K 线单源依赖已加固**（2026-09-11）：`fix_kline_server.py` 已加**多源 fallback**（TDX → **新浪不复权(主)** → 腾讯(备)）+ **TDX 早期熔断**；`data_readiness_gate` 已增查 `extra_factors` 末日期（重建窗口 16:00–21:20 豁免）。全市场 `--dry-run` 兜底实测 **4982/4991=99.8%**。源事实与坑（**腾讯 gtimg WAF 501 会封 IP**；688=股/其余=手）见 [`2026-09-11-kline-fallback-sources.md`](./2026-09-11-kline-fallback-sources.md)。
