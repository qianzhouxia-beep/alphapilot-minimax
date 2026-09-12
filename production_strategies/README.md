# 生产策略归档（Production Strategies Archive）

> **本文件夹是轨道 A + 轨道 B 全部落地生产代码的「唯一权威来源」（single source of truth）。**
> 所有修改必须在本文件夹内进行，并写入 `CHANGELOG.md`。
> 项目根目录中的同名文件是**旧副本/工作副本**，已冻结，不再修改。
>
> **选股模型 vs 买卖模型**：轨道 A 选股只在服务器，QMT/通达信只做买卖。改选股不用改交易端。详见 `knowledge/strategies/selection_vs_execution.md`。

> **⚠️ 文件命名铁律（2026-09-12 起）：文件名里的版本号 = 文件内的版本号。**
> 现行策略文件一律带版本号（如 `TrackB_track_b_qmt_auction_sim_v2.13.py`），升版 = **改名 + 重新部署**，文件名永远能自己说明版本。
> 旧快照/备份同样按其**真实内容版本**命名（如 `…_sim_v2.12.py`）。
> **权威文件 = 本文件夹内带版本号、且版本号与文件头一致的那一个**；不带版本号或版本号对不上的，一律视为历史副本。
>
> **行尾约定（2026-09-12，订正）**：`.py` 一律**保持各自原生行尾**，**禁止整文件重写行尾**（文本模式 `read_text/write_text` 会静默把 CRLF 变 LF，作废 md5 基线并让现场核对系统性假报警）。改动后请核对 `git diff --stat` 量级是否与改动相称。
> ⚠️ **不是"都该是 CRLF"**：实测本文件夹 CRLF 仅 4 个（`server/pre_market_gate.py` + 3 个模拟盘），其余 49 个 `.py` 为 LF ⇒ **6 个部署文件 = 2 CRLF + 4 LF**（逐文件见 §四）。现场核 md5 前**先确认该文件 `\r\n` 是否存在**，勿按"统一 CRLF"对表。
> **md5 基线冻结（2026-09-12）**：部署清单一旦发给现场，**在部署完成前不再做改名/引用同步等会改字节的动作**；否则基线会在同一天内反复移动（09-12 已三次：`a972e0a5…`→`3d76848a…`→`a360126e…`）导致现场假报警。基线以 §四 表为准，**部署后以现场文件反算**。

---

## 一、这是什么

双轨量化策略的**生产代码仓库**。轨道 A（现有链路）+ 轨道 B（竞价选股）共 6 个交易策略文件，
外加服务器导出脚本和设计/验证文档，全部归档于此。

## 二、目录结构

```
production_strategies/
├── README.md                 ← 本说明（权威规则）
├── CHANGELOG.md              ← 修改日志（每次改动必须追加）
│
├── track_a/                  ← 轨道 A（QMT/TDX 现有链路）
│   ├── TrackA_track_a_qmt_full_chain_sim_v2.45.py  v2.45      QMT 模拟盘（gene+path_fade+loud_vol+R5+TSDOWN+D8 + 条件式日内位置门 + peel 回撤上限2% + peel 次bar确认）
│   ├── TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py v2.38-tpl  QMT 实盘模板（gene+path_fade+loud_vol+R5+TSDOWN+D8；日内位置门 0.85 未改）
│   ├── TrackA_track_a_tdx_full_chain_sim_v2.31.py  v2.31      TDX 模拟盘（P2 + rank<=2, vwap 二次确认）
│   ├── fetch_tick_abr.py                 —          历史逐笔拉取 + ABR 聚合（mootdx）
│   ├── bt_abr_gate_fullchain.py          —          P2 买入 + ABR 门回测（双源合并）
│   ├── bt_abr_sell_early.py              —          ASR 卖出早退回测
│   ├── backfill_k5m_aug.py               —          mootdx 补 8 月 5m K 线
│   ├── _analyze_abr.py                   —          ABR 判别力分析
│   ├── _top10_dates.json                 —          回测候选合并计划（合并双源拉取）
│   └── BT_ABR_GATE_REPORT.md             —          ABR 门回测报告（2026-08-16）
│
├── track_b/                  ← 轨道 B（09:25-09:35 竞价选股）
│   ├── TrackB_track_b_qmt_auction_sim_v2.13.py        v2.13      QMT 模拟盘（LIM10-failsafe + LIM10 + path_fade + loud_vol + R5 + call-shadow）← 老板 QMT 部署此文件
│   ├── TrackB_track_b_qmt_auction_sim_v2.12.py   v2.12      ⚠️ 老板本地旧备份，**非部署目标**（QMT 部署的是上一行 v2.13）
│   ├── TrackB_track_b_qmt_auction_live_v2.7-tpl.py       v2.7-tpl   QMT 实盘模板（每账户一份）
│   ├── TrackB_track_b_tdx_auction_sim_v1.20.py        v1.20      TDX 模拟盘
│   ├── mootdx_feed.py                    —          免费逐笔数据服务（独立进程，非交易端内运行）
│   ├── mootdx_mock.py                    —          离线测试 mock
│   ├── _test_mootdx_feed.py              —          离线测试（17 项）
│   ├── _test_qmt_mootdx.py               —          QMT 接入 seam 测试（9 项）
│   ├── _test_buy_window.py               —          买入窗口 mock 回归测试（9 项，v1.1）
│   └── _test_fullpool_live_sync.py       —          fullpool_live 三端同步回归测试（19 项，v1.2）
│
├── ptrade/                   ← 轨道 A（Ptrade 端，备用链路）
│   ├── TrackA_track_a_ptrade_sim.py      v1.7        Ptrade 模拟盘（P2 + rank<=2, vwap 二次确认）
│   └── TrackA_track_a_ptrade_live.py     v1.7-tpl    Ptrade 实盘模板（每账户一份）
│
├── server/                   ← 服务器端
│   ├── export_qmt_scores.py              --fullpool 06:30 导出 fullpool
│   └── fix_kline_server.py               16:15 K 线补全（mootdx 串行，防并发限流）
│
└── docs/                     ← 设计 & 验证文档
    ├── TRACK_A_B_SELECTION_COMPARISON.md    v1.0   双轨全链选股策略对比（2026-08-17）
    ├── DUAL_TRACK_BRIEFING.md            v2.1   双轨设计简报（Harness 已交叉验证）
    ├── CODE_CROSSVALIDATION_BRIEFING.md  v1.0   代码级交叉验证任务书
    └── AGENT_RULES.md                    v1.0   给外部 Agent（Harness 等）的修改约束
```

## 三、修改规则（强制）

1. **所有修改只在本文件夹内进行**。项目根目录的同名文件视为历史快照，一律不改。
2. **每次修改必须在 `CHANGELOG.md` 追加一条记录**，格式见该文件头部模板。
3. 修改后必须通过 ASCII + 语法校验（QMT 文件必须**纯 ASCII**，否则 QMT 加密会报 `SyntaxError`）：
   ```bash
   python -c "import ast,pathlib; p=pathlib.Path(r'...'); b=p.read_bytes(); b.decode('ascii'); ast.parse(b.decode('ascii'))"
   ```
4. 任何 Agent（本会话、DeepSeek Harness、其他 AI）修改了生产文件，**同样必须把更新后的文件放回本文件夹并写日志**。
5. 版本号：改选股/卖出逻辑 → 升版本号（v1.0→v1.1）；只改配置/注释 → 不改版本号，只在日志说明。
6. **部署由用户手动执行**：Agent 只更新本文件夹（本地权威版），**不直接写交易端文件**（QMT 加密目录 / TDX `PYPlugins\user`）。用户会自行把本文件夹的文件复制/导入到 QMT 和通达信。Agent 在 CHANGELOG 里写明"需要部署到哪些交易端"即可，不做复制动作。

> ⚠️ **2026-08-29 约定固化**：之前 Agent 曾直接向 `D:\国金证券QMT交易端\...`、`D:\国金QMT交易端模拟\...`、`D:\new_tdx_mock\PYPlugins\user\...` 复制过文件（8-29 甜蜜区部署）。**此后一律不再直接复制交易端**，只更新本文件夹 + 写日志告知用户部署。

## 四、部署对照表

**md5 基线随本表冻结**（2026-09-12）。现场核对：**先看行尾（`\r\n` 是否存在）→ 再比 md5 → 再比 `[INIT]` 版本串**；三者任一不符才判"部署件≠仓库"。表值只对"本文件当前字节"有效，**每次改字节（含引用同步）都必须同步更新本表**。

| 文件 | 部署目标 | 行尾 | md5（权威 · 2026-09-12） | `[INIT]` 预期 |
|------|----------|------|--------------------------|----------------|
| `track_a/TrackA_track_a_qmt_full_chain_sim_v2.45.py` | QMT 模拟盘 python 目录（明文复制，勿粘贴） | **CRLF** | `4d43f181cc804d597723c0df9cf62fec` | `track-A qmt-sim v2.45 (… cond-dayhigh, peel-cap2%+nextbar)` |
| `track_a/TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py` | QMT 实盘，每个账户复制一份，改 CONFIG 块 | LF | `34d62a96410e58f16e66700b32eaa49d` | `track-A qmt-live v2.38-tpl (…)` |
| `track_a/TrackA_track_a_tdx_full_chain_sim_v2.31.py` | TDX 通达信量化端 `PYPlugins\user` 目录 | LF | `924a3bf99809ab1c98abd124cb28bd4c` | `track-A tdx-sim v2.31` |
| `track_b/TrackB_track_b_qmt_auction_sim_v2.13.py` | QMT 模拟盘（**第二个模拟账户**），python 目录 | **CRLF** | `a360126e16b8609ba30d69b8fd4b033b` | `track-B v2.13 (LIM10-failsafe+LIM10+…)` |
| `track_b/TrackB_track_b_qmt_auction_live_v2.7-tpl.py` | QMT 实盘，每账户一份，改 CONFIG | LF | `7e1d1a86df85c6d0a2c04ed96bac378c` | `track-B v2.7-tpl (auction-select, vwap 2nd)` |
| `track_b/TrackB_track_b_tdx_auction_sim_v1.20.py` | TDX 量化端 `PYPlugins\user`（独立 `.py` 运行） | LF | `03de7b1bbac8b846bcc7d0f48966a686` | `track-B tdx v1.20` |
| `track_b/mootdx_feed.py` | 本机独立 Python 环境（已 `pip install mootdx`），交易日 09:15 启动常驻 | — | — | — |
| `server/export_qmt_scores.py` | 服务器 `/home/ubuntu/alphapilot/`（scp 覆盖） | — | —（待其未提交改动定稿后补） | — |
| `server/fix_kline_server.py` | 服务器 `/home/ubuntu/alphapilot/`（scp 覆盖；16:15 cron 补 K 线） | — | —（同上） | — |

> 注：`live`/`tdx` 模板与 `tdx sim` 在仓库中为 **LF**（历史如此，非本次改）；`A sim v2.45`、`B sim v2.13` 为 **CRLF**。§四 md5 与 `a972e0a5…`/`3d76848a…` 等历史值**互不复用**——历史值仅见于 CHANGELOG / checkpoints 审计条目。

## 五、数据链路速览

```
服务器 06:30 export_qmt_scores.py --fullpool
  → output/qmt_scores/{date}.fullpool.json   ← 轨道 B 数据源（09:36 前兜底）
服务器 09:35 live_momentum_scanner（全市场实时资金流重排 score=0.6管线+0.4动量）
  → 09:35 morning_live_fund_select（资金门 money_flow_pass + 研报门 research_tier）
  → 09:36 export_qmt_scores.py --fullpool-live
  → output/qmt_scores/{date}.fullpool_live.json  ← 轨道 B 实时池（09:36 后主用）
服务器 09:36 export_qmt_scores.py
  → {date}.json + {date}.candidates.json     ← 轨道 A 数据源
nginx /qmt_scores/ 静态托管
本地 QMT/TDX 缺文件时自动从 http://150.158.100.236/qmt_scores/ 拉取

mootdx_feed.py（本机独立进程，交易日 09:15-15:00）
  → 通达信行情服务器逐笔成交（free，含买卖方向）
  → C:\alphapilot\l2_feed\{date}.json         ← 轨道 B 主动买占比 + 轨道 A ABR 买入门（替代 QMT L1 近似）
```

**轨道 B 实时选股（2026-08-17 新增）**：QMT 模拟盘在 09:36 后自动切到
`{date}.fullpool_live.json`——该文件由服务器 09:35 `live_momentum_scanner`
（0.6×管线106维因子 + 0.4×全市场实时资金动量）＋ `morning_live_fund_select`
（资金门 + 研报门）重排后导出，因此 Track B 用上了 5:00 管线的**全部因子与门控**，
而不再只有资金/量比。QMT 端只保留 ABR 实时软复检 + P2 动态确认（价>VWAP、不追高、
5m 放量）作为最终买入触发。09:36 前 / live 文件缺失时回退 05:00 fullpool 经典流程。
对比回测（08-03~08-14，9 天 T+1）：实时池累计 +64.12% vs 静态池 +37.52%。

**轨道 A ABR 门（v2.13）**：QMT/TDX 三份策略文件的 P2 动态确认触发后，连续竞价
时段（≥09:30）检查主动买占比——QMT 优先读 `C:\alphapilot\l2_feed\{date}.json`
（mootdx_feed），回退 QMT L1 逐笔近似；TDX 用盘口买一档量近似。低于
`MIN_ACTIVE_BUY=0.52` → `skip_low_abr` 当日放弃。**软门**：数据不可用不拦截。
部署 QMT 轨道 A 前需先启动 `mootdx_feed.py`。

## 六、当前版本基线（更新 2026-09-12；文件名版本 = 文件内版本）

| 文件 | 版本 | 状态 |
|------|------|------|
| 轨道 A QMT 模拟（`TrackA_track_a_qmt_full_chain_sim_v2.45.py`） | v2.45 | ✅ peel 回撤上限2% + peel 次bar确认 |
| 轨道 A QMT 实盘模板（`TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py`） | v2.38-tpl | ✅ 实盘模板（落后模拟，正常） |
| 轨道 A TDX（`TrackA_track_a_tdx_full_chain_sim_v2.31.py`） | v2.31 | ✅ TDX 模拟盘 |
| 轨道 B QMT 模拟（`TrackB_track_b_qmt_auction_sim_v2.13.py`） | v2.13 | ✅ LIM10 fail-safe + ACCOUNT_ID=62128716（**老板 QMT 部署件**） |
| 轨道 B QMT 实盘模板（`TrackB_track_b_qmt_auction_live_v2.7-tpl.py`） | v2.7-tpl | ✅ fullpool_live 实时池已同步 |
| 轨道 B TDX（`TrackB_track_b_tdx_auction_sim_v1.20.py`） | v1.20 | ✅ fullpool_live 实时池已同步 |
| 服务器 fullpool 导出 | --fullpool | ✅ cron 06:30 已就绪 |
| 服务器 fullpool_live 导出 | --fullpool-live | ✅ cron `36 9 * * 1-5` 已部署（2026-08-17） |
