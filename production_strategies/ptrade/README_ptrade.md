# AlphaPilot Ptrade 迁移部署指南

把 AlphaPilot 的 Track A / Track B 全链路策略（原 QMT 版）迁移到 **Ptrade（恒生）** 平台的部署文档。
Ptrade 运行在券商云端虚拟机（如湘财证券），策略必须以**单个 .py 文件**形式在"交易"模块中运行。

---

## 1. 文件清单

| 文件 | 用途 |
|------|------|
| `TrackA_track_a_ptrade_sim.py` | Track A 模拟盘策略（先部署这个验证） |
| `TrackA_track_a_ptrade_live.py` | Track A 实盘模板（验证通过后克隆，改 CONFIG） |
| `ptrade_adapter.py` | API 适配层（研究环境可复用；策略文件已内嵌同等实现） |
| `_test_tracka_ptrade.py` | 离线逻辑测试（P2/卖出/轮动/滑点/代码转换） |

> 后续：Track B（`TrackB_track_b_ptrade_auction_sim.py` / `_live.py`）迁移在 Track A 跑通后进行。

---

## 2. 与 QMT 版的关键差异

| 差异 | QMT 版 | Ptrade 版 |
|------|--------|-----------|
| 代码格式 | `600519.SH` / `000001.SZ` | `600519.SS` / `000001.SZ`（沪市用 `.SS`） |
| 策略入口 | `init(C)` / `handlebar(C)` | `initialize(context)` / `handle_data(context, data)`（分钟周期） |
| 实时行情 | `get_market_data_ex(period="tick")` / `get_full_tick` | `get_snapshot(code)` |
| 日 VWAP | `get_full_tick` 的 `amount/pvolume` | `get_snapshot` 的 `wavg_px`（券商直接给，无手/股单位换算） |
| 换手率 | `volume / FloatShares` | `get_snapshot` 的 `turnover_ratio` |
| 涨停判断 | `get_instrument_detail` 的 `UpStopPrice` | `get_snapshot` 的 `up_px` |
| 持仓/资金 | `get_trade_detail_data(ACCOUNT_ID,"STOCK",...)` | `get_positions()` / `context.portfolio` |
| 下单 | `passorder(23/24, ..., ACCOUNT_ID, ...)` | `order(security, amount)`（正买负卖；拒绝时返回 `None`） |
| 主动买占比(ABR) | mootdx 本地进程 / QMT L1 tick | L2 `get_individual_transaction` 优先，否则快照内/外盘近似 |

**ABR 门控（Level 2）**：若湘财账户开通了 L2，策略自动用逐笔成交方向算 ABR；
若无 L2，降级用快照的 `business_amount_in/out`（内/外盘）近似；数据仍不可用则**软门通过**（与 QMT 版 mootdx 缺失时行为一致）。**策略不会因为缺 L2 而停摆。**

---

## 3. 数据通路（分数 JSON 如何进入 Ptrade 云端）

Ptrade 云端**默认无法直接访问外网**，也不能读你本机的文件。两条通道，策略自动按顺序尝试：

### 通道 A：HTTP 直连服务器（推荐，实时性最好）
- 策略 `REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"`
- 服务器 nginx 静态目录已暴露 `output/qmt_scores/` 下的 `{YYYYMMDD}.json` 和 `{YYYYMMDD}.candidates.json`
- **需要申请**：让朋友联系湘财证券客户经理，申请该策略的**外网白名单**（出站 HTTP 访问上述 IP:80）。
- 开通后策略盘中每 60 秒拉取一次最新候选池。

### 通道 B：定时上传（无白名单时）
1. 在你（AlphaPilot 服务器或你本机）定时把分数文件同步到朋友的电脑某目录。
2. 朋友在 Ptrade 客户端的"研究"模块配置**定时上传**，把文件传到云端的 `upload_files/` 目录。
3. 策略通过 `get_research_path() + "/upload_files/"` 读取。

> 策略的读取顺序：`HTTP → upload_files → research 根目录`，第一个能解析的 JSON 生效。
> 文件命名必须与服务器一致：`{YYYYMMDD}.candidates.json`（Track A 优先用这个），
> 没有时回退 `{YYYYMMDD}.fullpool.json` / `{YYYYMMDD}.json` 前 10 名。

---

## 4. 部署步骤（Track A 模拟盘 → 实盘）

### 4.1 模拟盘
1. 登录 Ptrade 客户端（湘财），进入**量化 → 策略**，新建策略。
2. 周期选 **分钟（minute）**，把 `TrackA_track_a_ptrade_sim.py` 全文粘贴进去。
3. 账户选**模拟账户**，运行。
4. 观察日志应出现：
   ```
   [INIT] track-A ptrade v1.7 (P2 + rank<=2, vwap 2nd) sim
   [INIT] L2 available: True / False
   [FILE] 20260819.candidates.json <- HTTP ok   (或 <- <upload_files 路径>)
   ```
5. 盘中核对：`[CAND]`（候选池）、`[BUY]` / `[SELL]` / `[ROT]` / `[EXT]` 是否正常触发，
   `[LEDGER]` 收盘快照是否生成。

### 4.2 实盘
1. 复制 `TrackA_track_a_ptrade_live.py`，每个实盘账户一份。
2. 只改文件顶部 **CONFIG 块**：
   - `ACCOUNT_TAG`（如 `"alice_live"`，用于隔离锁/日志文件）
   - `ALLOW_STAR / ALLOW_CHINEXT / ALLOW_BSE`（该账户实际开通的板块权限）
   - `POSITION_PCT / MAX_HOLDINGS / MAX_DAILY_BUY`（该账户风控）
3. 新建实盘策略粘贴该文件，绑定**实盘交易账户**，运行。
4. 启动后确认日志 `[INIT] ... LIVE | tag=...`，再投入资金。

### 4.3 部署注意事项
- **纯 ASCII**：策略文件不含中文字符（Ptrade 老版 Python 环境要求）。
- **无 f-string**：为兼容老版本 Python 3.5+，所有字符串拼接用 `+` / `%`。
- **单文件**：不要依赖 `import ptrade_adapter`——实盘策略无法跨文件引用，适配函数已内嵌。
- **文件写入限制**：Ptrade 策略沙箱可能禁止写文件。若日志没有锁/成交文件生成，订单去重
  会退化为会话内存 + 持仓同步（可接受，但策略重启后当日已下单记录会丢失，靠持仓同步兜底）。

---

## 5. 模拟盘验证清单

在正式实盘前，至少在模拟盘连续跑 1 周，逐项确认：

- [ ] 开盘前分数文件成功加载（HTTP 或 upload_files）
- [ ] 09:35 后 P2 动态确认正常触发买入（`[BUY] ... P2=dyn_confirm`）
- [ ] 涨停股不追（`[WAIT] ... limit-up skip`）
- [ ] 高换手过滤（`[WAIT] ... P2=skip_high_turnover`）
- [ ] 滑点保护（`[BUY] ... slip guard: live > trig ... hold off`）
- [ ] 买入数量 ≤ 可用现金（`POSITION_PCT × 总资产`）
- [ ] T+2 动态强平 / 盈利延长 T+3（`[EXT]` / `t2_force` / `t2_force_after_extend`）
- [ ] 弱势轮动（持仓满 + P2 候选通过 → `[ROT] sell` 最弱持仓）
- [ ] VWAP 早退、Wyckoff 出货、跌停止损各触发路径
- [ ] 收盘 `[LEDGER]` 快照与账户实际持仓一致
- [ ] 板块权限：未开通板块的候选被 `[SKIP] board not allowed` 过滤，无废单

---

## 6. 已知风险与说明

1. **Level 2 权限（湘财）**：目前不确定朋友账户是否开通。已做三级降级（L2 → 内外盘 → 软门），
   无 L2 也能跑，但 ABR 门控精度降低。建议朋友向客户经理确认是否可开通 L2。
2. **HTTP 白名单**：能否外网访问服务器需湘财批准，未批准前必须走 upload_files 通道。
3. **模拟盘 vs 实盘滑点**：模拟盘成交价通常按触发价，实盘有滑点；策略内已有
   `MAX_BUY_SLIP_PCT` 保护，但建议实盘初期用小仓位。
4. **云端时区**：Ptrade 云端与 A 股同在北京时区，`datetime.now()` 直接可用。
5. **策略重启**：Ptrade 策略重启后 `position_map` 从账户持仓重建，`buy_date` 通过
   当日 `get_trades()` 推断（今天买入且 `can_use < shares` → T+1 锁定）。

---

## 7. 服务器端分数文件说明（供定时上传配置）

服务器 `production_strategies/server/export_qmt_scores.py` 每天产出（`output/qmt_scores/`）：

| 文件 | 内容 | Track A 用途 |
|------|------|-------------|
| `{YYYYMMDD}.json` | `{code: score}` 全量评分 | 兜底（取前 10） |
| `{YYYYMMDD}.candidates.json` | `{"date", "candidates":[{symbol,name,score,rank}]}` | **首选** Top10 候选池 |
| `{YYYYMMDD}.fullpool.json` | 06:30 全池（含 5d 主力净额） | Track B 竞价候选 |

定时上传的朋友电脑侧，同步目录应包含当天的 `{YYYYMMDD}.candidates.json`（及可选 `fullpool_live.json`）。
