# AlphaPilot 项目长期记忆（Cursor ↔ WorkBuddy 共享）

> 双方 Agent 必读。结论性规则写这里；详细论证见 `knowledge/` / `docs/`。
> 最后更新：2026-09-11

---

## 协作者代号（2026-09-10 用户拍板）

- **WorkBuddy 的正式代号 = `WB`**（用户确认沿用，不改名）。所有文档 / 脚本 / Issue 回帖 / 会话引用统一用 `WB`；跨会话长期有效。

---

## 服务器操作分工约定（2026-09-06 用户拍板）

**原则：需要上传服务器 / 在服务器上做变动的，Agent 直接执行，不再询问、不交给用户。**

- 背景：服务器（上海 ECS `/home/ubuntu/alphapilot`）的上传/变更历来由 Agent 完成，用户从未参与。
  如果让用户手动操作，容易漏传（资金三角影子 9 天空转的根因之一就是模块漏传服务器）。
- 适用范围：**服务器端一切文件与操作**（scp 覆盖、补传模块、cron 变更、运行脚本等）→ Agent 直接做。
- 例外（仍由用户手动）：**交易端文件**（QMT python 目录 / TDX `PYPlugins\user`）— 见
  `.cursor/rules/production-strategies.mdc` 规则 5「部署由用户手动执行」，用户会自行复制/导入模拟端与实盘端。
- 执行纪律：Agent 每次服务器变更后照常自验（py_compile / md5 比对 / 关键字段计数），并在 CHANGELOG / checkpoint 留痕。

---

## 代码流向铁律 + 量化两端模型（2026-09-11 用户拍板）

**代码流向：仓库 → 服务器（repo-first）。** 先改仓库，再从仓库推送到服务器；**不再"在服务器上直接改"**（新加坡服务器旧流程即如此）。
⇒ **仓库 = 代码之源**；服务器 = 部署目标。（数据新鲜度另论：数据仍以 SSH 上海机闸门为准。）

**量化两端（必须分清）：**

| 端 | 是什么 | 代码在哪 |
|---|---|---|
| **选股端** | 产生候选：05:00 管线 / 09:35 scanner / 09:36 导出 | 服务器 `/home/ubuntu/alphapilot`（已镜像回仓库） |
| **交易端** | QMT/通达信执行买卖：买哪个 / 卖哪个 / 怎么卖 | **本地** `production_strategies/track_a` + `track_b`（+ `ptrade/`）的 live/sim 代码 |

- ⚠️ **看 QMT 买卖逻辑，请查本地 `production_strategies/`，不要去服务器找。**
- 服务器上的 `trade_executor.py` + `data/paper_trading.json` 是**选股端自带的服务器纸面模拟**，**不是 QMT 交易端**（勿再把它的规则当成"生产真实出场"）。
- 交易端版本：Track A 实盘 `TrackA_track_a_qmt_full_chain_live.py`（v2.38-tpl）/ 模拟 `..._sim.py`（v2.45）；Track B `TrackB_track_b_qmt_auction_live.py` / `..._sim.py`。实盘落后模拟若干版本属正常。
- 部署分工：**交易端由用户手动**复制到 QMT/TDX（规则 5）；**服务器端由 Agent 直接部署**。

---

## 日常验证分工约定

**生效日：2026-08-26 起。** 原则：**PASS 静默、FAIL 才报。** 全绿 = 当没这回事。

| 环节 | 状态 | 职责 |
|---|---|---|
| 上传前校验 | ✅ 已上线 | WorkBuddy — `_upload_chip_template.py` 内嵌 `check_chip_batches.py`，FAIL 即 `exit(1)` 物理拦截 |
| 服务器闸门 | ✅ 已上线 | Cursor/服务器 — `18:15 daily_coverage_check` + `04:50 data_readiness_gate` cron 自动跑 |
| 失败才告警 | ✅ 已上线 | Cursor/服务器 — `data_readiness_gate` 仅 critical **FAIL** 推 WeCom；`ready=True` 静默（同日同 sig 去重） |
| WorkBuddy 侧报告 | ✅ 已上线 | WorkBuddy — PASS 不发「今日已通过」长报告；FAIL 才主动报 |

**用户侧**：不再每天问「数据拉好没」。只有失败（校验 FAIL / 上传失败 / WeCom 告警 / 05:00 管线异常）才打扰。

**08-24 半截上传事故整改**：至此封口（2026-08-25 闭环确认）。

关联文档：
- `production_strategies/docs/WORKBUDDY_CHIP_UPLOAD_RULES.md`
- `production_strategies/server/check_chip_batches.py`
- `scripts/data_readiness_gate.py`（`maybe_wecom_push_fail`，`WECOM_READINESS_PUSH=0` 可关）
- `docs/WB_筹码上传校验报告_2026-08-25.md`
- `docs/LOG_2026-08-25.md`

---

## K 线单位铁律（2026-08-22 用户拍板）

**判定统一用 `amount / (volume × close)`：**

| ratio | 含义 | 动作 |
|---|---|---|
| ≈1 | 已是股 | **别动** |
| ≈100 | 是手 | **×100 转股** |

- 缓存口径 = **股**；通达信源 = **手**。
- 禁止仅凭列名判断；ratio≈100 才 ×100。
- **WorkBuddy**：K 线只读不写；归 cron `15 16 * * 1-5` + 已部署 `fix_kline_server.py`。

详述：`docs/CURSOR_K线单位铁律_2026-08-22.md`

---

## 交易时点铁律（2026-09-11 双方复核定案）⚠️

**生产的「选股日 = 买入日 = 归档文件夹日 D」，上午当日内完成：**
`09:25:55 竞价快照 → 09:35 全市场终选 → 09:36 自动买入 → 09:40 归档`。

- **入场 = 选股日 D 当天 09:36**，**不是**次日 D+1。
- ⇒ **D 日收盘后的信息**（D 日 EOD 板块资金流、D 日收盘价）**在入场时不可得**；把"截止 D"的状态用于 D 日入场**就是前视**。
- ⇒ 研究里惯用的 "归档日 D + 次日 D+1 开盘买" 是**研究口径，比生产晚一天**；**相对结论或不翻，但绝对收益 / 时点类结论须重算**。
- ⚠️ **`daily_picks_archive/<D>/top2.json` 的 `buy_price` 不是成交价**（2026-08-03→08-21 间歇性坏：25.5% 落在当日 [low,high] 外、31.4% = D−2 收盘）；模拟盘 `paper_trading.json` `trade_log` 曾直接拿它记账 → 该段收益被高估。**勿再把它当入场价。**
  - **根因（已定位）= 选股时那份 K 线缓存的最后一根收盘 → 缓存滞后几天，`buy_price` 就等于 D−k 收盘。** 不是公式错，是**上游缓存不新鲜**（东财被风控期间滞后 2 天；08-25 起变 None 后 fallback 实时价 = 换个错法）。
- ⚠️ 归档目录**缺 5 个交易日**（07-28/07-29/07-31/08-04/08-24）；**缺目录 ≠ 当天没交易**。**根因 = `archive_daily_picks.py::_day()` 用源文件 `asof` 当目录名，源滞后时重写前一天目录**（07-27 被连写 3 次）⇒ **有效信号日 ≈29，不是 33**。
- ⚠️ **K 线缓存新鲜度是总病根**：东财风控/腾讯 qfq 滞后/TDX 服务端中断都会污染下游。09-10 缺口已用"腾讯/westock 单日合并（三重校验+原子写）"修复，见 `knowledge/data_sources/2026-09-11-kline-0910-recovery.md`。
  - **09-11 已加固**：`fix_kline_server.py` 加 **TDX 早期熔断 + 多源兜底（TDX → 新浪不复权(主) → 腾讯(备)）**；闸门增查 `extra_factors` 末日期。**腾讯 gtimg WAF 高频会 501 封 IP → 只做备源**；688=股/其余=手。详见 `knowledge/data_sources/2026-09-11-kline-fallback-sources.md`。

详述：`knowledge/data_sources/2026-09-11-production-entry-timing.md` ·
`knowledge/data_sources/2026-09-11-sim-ledger-buyprice-bug.md`

---

## 关键数据发现

- 生产 chip **只认 WorkBuddy 上传的东财真实 CYQ**，不用 `pull_chip_from_kline.py` 推演兜底。
- 服务器数据真相以 **SSH 上海机** `data_readiness_gate.py` 为准，不以本地 stale 文件为准。
- 生产模型 = V25 **106 维**（不是 fd1 实验 116 维）。

---

## 选股模型 vs 买卖模型（必须分开讲）

- **选股模型** = 服务器（05:00 管线 / 09:35 scanner / 09:36 导出）。决定候选池和排名。改选股 **不用改** QMT/通达信。
- **买卖模型** = QMT / 通达信。读 `{date}.candidates.json` Top10，P2 确认后下单、再按规则卖出。只有改 P2/仓位/卖出才动交易端。
- ⚠️ **买卖模型的权威代码在本地 `production_strategies/track_a` / `track_b` 的 live/sim**，不在服务器（见上节"代码流向铁律 + 量化两端模型"）。
- 网页融合 Top10 是选股展示榜，**不是**买卖模型的下单顺序。
- 详述：`knowledge/strategies/selection_vs_execution.md`
- **Checkpoint 目录**（做过什么 / 还要盯什么）：`knowledge/ops/checkpoints.md`

## 生产策略唯一权威来源

`production_strategies/` — 轨道 A/B 落地代码只改此目录；根目录同名文件冻结。

---
