# 同花顺官方金融数据（HiThink / Fuyao）

> 接入日：2026-08-22  
> 角色：**补缺口**，不替换 Sina / 腾讯 / mootdx 主行情  
> 生产排序：**不加**（见 `knowledge/signals/hithink_p2_t1.md`）  
> 以后要用：先读本文，再调 MCP 或 REST；Key 不进 git

## 这是什么

同花顺 **HiThink Financial-API**（产品名 Fuyao）。GitHub：`HiThink-Tech/Financial-API`。文档：`https://fuyao.aicubes.cn/docs/`。

我们已有 Sina/腾讯快照、K 线 parquet、资金流、筹码、mootdx 逐笔。这个源补的是那些源**没有或不稳**的字段：涨停/跌停/炸板池、连板天梯、热股榜、龙虎榜、集合竞价、个股异动原因。

**不覆盖**：分钟 K、L2 逐笔、期货、外盘、A50、金银油。那些继续用现有源 / 情报层。

## 认证（Key 禁止进仓库）

| 优先级 | 位置 |
|---|---|
| 1 | 环境变量 `HITHINK_FINANCE_API_KEY` 或 `FUYAO_TOKEN` |
| 2 | 服务器 `/home/ubuntu/alphapilot/config/hithink_api_key.conf`（0600） |
| 3 | 本机 `C:\Users\elvisq\.hithink_finance_api_key` |

REST：`https://fuyao.aicubes.cn`，请求头 `X-api-key`。成功业务码 `code=0`。

**禁止**把 Key 写进代码、日志、知识库、commit。探针脚本 `bt_research/_probe_hithink.py` 只从环境/主目录读。

## 已落地文件

| 路径 | 作用 |
|---|---|
| `scripts/hithink_overlay.py` | 工作日 **15:40** 只读落盘（服务器 cron） |
| `hithink_p2_side.py` | 09:35 旁支标注；`HITHINK_P2_SIDE` **默认 0**，不改 `score` |
| `output/hithink_overlay.json` | 最新指针 |
| `output/hithink_archive/YYYY-MM-DD.json` | 按日归档 |
| `bt_research/bt_hithink_p2_factors.py` | as-of 回测；缓存 `bt_research/_hithink_cache/` |

## 以后怎么取数

**对话里优先走 Cursor MCP**（已接，不必手写 HTTP）：

- `user-fuyao-a-share`：行情快照/历史 K、涨停跌停炸板、热股、龙虎榜、竞价、交易日历、财务估值
- `user-fuyao-a-share-index`：同花顺板块目录 / 成分 / 指数行情
- `user-fuyao-fund`：公募基金
- `user-fuyao-meta`：`thscode` 检索

脚本/cron 用 REST（见下表）。标的代码必须是 `600519.SH` / `000001.SZ` / `300750.SZ`，不要传纯 6 位。

### 特色数据（我们真正缺的）

| 能力 | 路径 | 历史怎么查 | as-of 注意 |
|---|---|---|---|
| 涨停池 | `GET /api/a-share/special-data/limit-up-pool` | `date_ms`=上海 00:00 毫秒戳；`page/size`（size≤200） | T 日 09:35 **不能**用 T 收盘池；用 T-1 |
| 跌停池 | `.../limit-down-pool` | 同上 `date_ms` | 同上 |
| 炸板池 | `.../limit-break-pool` | 同上 `date_ms` | 同上 |
| 连板天梯 | `.../limit-up-ladder` | 近 30 日矩阵，无自定义窗口 | 当日快照 |
| 热股榜（当前） | `.../hot-stock-list?period=day` | `day`=24 小时榜，09:35 常含隔夜热度 | 不要当「今天早盘热度」 |
| 热股榜（历史） | `.../hot-stock-list-history?date=YYYY-MM-DD` | 自然日字符串 | 回测用这个 |
| 热股排名走势 | `.../hot-stock-rank-trend` | 单只 + 日期区间 | 一次一只 |
| 龙虎榜 | `.../dragon-tiger-list` | `date=YYYY-MM-DD`，`board_type=all/org/hot_money` | T 日 09:35 用 T-1 |
| 个股异动 | `.../anomaly-analysis-stock` | **仅当日**，无历史 | 不能回测 |
| 飙升榜 | `.../skyrocket-list` | 仅当日 | 与热股榜不是同一套排名 |

### 行情 / 日历（对照或补洞，不替换主 K 线）

| 能力 | 路径 | 注意 |
|---|---|---|
| 快照 | `GET /api/a-share/prices/snapshot?thscodes=` | 无中文名；省略 thscodes 会拉全市场 |
| 历史日 K | `GET /api/a-share/prices/historical` | **一次一只**；`interval=1d`；`start/end` 毫秒；`adjust=none/forward/backward` |
| 交易日历 | `GET /api/a-share/calendar/trading-days` | 返回日多为 **`YYYYMMDD`**，用前必须归一成 `YYYY-MM-DD` |
| 竞价快照 | `GET /api/a-share/auction/snapshot?thscodes=` | 实时/终态；**无历史接口**，回测竞价规则测不了 |
| 板块目录 | `GET /api/a-share-index/catalog/ths-index-list?tag=cn_industry` | 同花顺行业，不等于我们的 `stock_industry_map.json` |

`date_ms` 必须是 Asia/Shanghai 当天 00:00 的 Unix 毫秒，不要传 `YYYY-MM-DD` 给涨停池。

## 和现有源怎么分工

| 需求 | 用谁 |
|---|---|
| 日 K / 量价主库 | `data/kline_cache/kline_all.parquet`（volume=股） |
| 09:35 选股打分 | VM2.5 + `morning_live_fund_select.py`，**不读本源改分** |
| 盘中逐笔 ABR | mootdx `l2_feed` |
| 涨停原因 / 连板 / 封单 / 炸板 | **本源** |
| 热股 / 龙虎榜官方榜 | **本源**（我们也有 `pull_lhb_history.py`，两套可对照） |
| 集合竞价 | 本源快照 + 现网 `pre_market_gate`（**仅用竞价 gap/板块强弱；竞价量字段 `pre_market_call_amount_wan` 只记录不消费**——A/B 两端均未用。竞价量正确用法=R5-CALL 反向否决，见 2026-09-05 R5）；本源无历史 |
| 隔夜外盘 / 商品 | 情报层 `intel_sweep.py`，本源没有 |

## 生产与回测结论（2026-08-22）

把 T-1 涨停/热股/龙虎榜加进 P2 Top2 排序：**否决**。14 个生产日拟议 ±8%/12% 旁支分换人 0 天；硬剔除昨日涨停 T+1 +0.48%→+0.12%。热股前 10 在 gated 池命中 0。详情：`knowledge/signals/hithink_p2_t1.md`、`output/bt_hithink_p2_factors.md`。

以后若再接到选股：**先 as-of 回测，有增量再开 `HITHINK_P2_SIDE=1`**。不准硬加，也不准因为「担心」而拒绝回测。

仍建议继续跑 15:40 归档，给人复盘、给以后复验攒样本。

## 实测（2026-08-21 干跑）

涨停 54 / 跌停 13 / 炸板 18 / 热股 30 / 龙虎榜 61。9/9 源成功。快照价与新浪一致（例：002580）。延迟约 220–350ms。

## Agent 取用清单

1. 读本文 + `knowledge/data_sources/index.md` 对应节。
2. 对话查询：调 `user-fuyao-*` MCP。
3. 脚本落盘：复用 `scripts/hithink_overlay.py` 的 `load_key()` / `get_json()`，不要复制 Key。
4. 回测：特征只用 T-1 特色数据；日历字段先规范化；K 线可用本源 `prices/historical` 或项目 parquet。
5. 改生产选股前：必须有增量数字，并写 `production_strategies/CHANGELOG.md`（本源旁支若改 `morning_live_fund_select.py` 也要说明开关默认值）。
