# AlphaPilot 交接：给另一台电脑上的新 WorkBuddy

> 写给：**刚装好的 WorkBuddy 应用端**。用户会把这份文件发给你，让你分担 AlphaPilot 工作。
> 写成日：**2026-09-02**。细节以仓库里的权威文件为准，本文只指路，不复制全书。
> **不要把本文件里的服务器路径、交易端路径写进公开仓库以外的地方；不要向用户索要、也不要回显密钥 / PEM / Webhook / 账户号。**

---

## 0. 你是谁、先干什么

你是 **WorkBuddy**，和本机 Cursor Agent 是同一项目的两个执行端。Cursor 通常在用户主工作电脑上；你可能在另一台电脑上。你们读同一套仓库规则，写同一套知识库。

**先做这 5 步，再接任何具体任务：**

1. 确认用户已经在本机打开 **AlphaPilot 仓库**（git clone / 同步副本）。没仓库就先让用户打开，不要凭印象改生产。
2. 按顺序读：**`AGENTS.md` → `MEMORY.md` → 本文 → `knowledge/ops/checkpoints.md` 最上面约 15 行**。
3. 再读：`production_strategies/docs/AGENT_RULES.md`。若今天要动筹码，再读 `production_strategies/docs/WORKBUDDY_CHIP_UPLOAD_RULES.md`。
4. 问用户今天要你分担哪一类（数据 / 核查 / 回测 / 买卖规则 / 选股脚本）。**没指定就先只读 checkpoints，不要改生产。**
5. 动手前在 `knowledge/ops/checkpoints.md` 看有没有别人刚改过同一层；改完必须回写知识库（见第 8 节）。

---

## 1. 项目一句话

**AlphaPilot** = A 股量化：**服务器选股** + **QMT/通达信买卖** + **研发车间**。生产跑在上海服务器 `/home/ubuntu/alphapilot`。前端在 Zeabur。

两层必须分开讲（违反即混层）：

| 层 | 干什么 | 代码在哪 | 改完要不要动交易端 |
|---|---|---|---|
| **选股模型** | 选哪只、排什么序 | 服务器脚本 + `export_qmt_scores.py` | **不用** |
| **买卖模型** | 何时买、买几只、何时卖 | 只改 `production_strategies/track_a/` `track_b/` `ptrade/` | **要**（用户手动复制，你禁止直接写 QMT/TDX 目录） |

权威对照：`knowledge/strategies/selection_vs_execution.md`。

网页 09:38 融合 Top10 **不是**下单顺序。QMT 读的是 `{date}.candidates.json` 的 09:35 名次。

---

## 2. 必读清单（按需下钻，不要一次读完仓库）

| 优先级 | 文件 | 用途 |
|---|---|---|
| P0 | `AGENTS.md` | 所有 Agent 入口 |
| P0 | `MEMORY.md` | Cursor ↔ WorkBuddy 共享铁律（筹码、K 线、PASS 静默） |
| P0 | `knowledge/ops/checkpoints.md` | 「上次改了啥 / 还要盯啥」，先看这个再下钻 |
| P0 | `production_strategies/docs/AGENT_RULES.md` | 外部 Agent 改生产的硬约束 |
| P0 | `production_strategies/README.md` + `CHANGELOG.md` | 生产文件清单、当前版本、部署对照 |
| P1 | `knowledge/INDEX.md` | 知识库地图 |
| P1 | `knowledge/strategies/buy_sell_rules.md` | 买卖规则 |
| P1 | `knowledge/models/v25_106d.md` | 生产模型 = **V25 106 维**（不是 fd1 的 116 维） |
| P1 | `knowledge/decisions/index.md` | 为什么做 / 为什么没做 |
| P1 | `production_strategies/docs/WORKBUDDY_CHIP_UPLOAD_RULES.md` | 筹码上传（你的招牌职责） |
| P1 | `CONTEXT-MAP.md` | 生产 vs `rd_workshop/`：互相只读，晋升必须人工 |
| P2 | `knowledge/strategies/0935_momentum_scanner.md` | 09:35 双路径 |
| P2 | `knowledge/data_sources/index.md` + `hithink.md` | 数据源；同花顺官方 API **不进 09:35 打分** |
| P2 | `docs/CURSOR_K线单位铁律_2026-08-22.md` | K 线「股 vs 手」 |

`docs/` 里大量 `WORKBUDDY_*.md` / `给WorkBuddy的同步稿_*.md` 是历史讨论稿，**结论以 `knowledge/` 和 `MEMORY.md` 为准**。

---

## 3. 和 Cursor 怎么分工、怎么避免撞车

历史默认分工（`MEMORY.md`）：

| 谁 | 默认职责 |
|---|---|
| **WorkBuddy** | 东财真实 CYQ **筹码拉取 + 上传**；交叉验证；用户指定的核查/回测 |
| **Cursor / 服务器 cron** | K 线写入（`fix_kline_server.py`）、数据闸门、05:00 管线、09:35 选股、大部分买卖代码改动 |
| **用户** | QMT / 通达信 **手动部署**；拍板晋级 |

你在**另一台电脑**上时，能力边界先自检：

| 本机有没有 | 你可以做 | 不要假装能做 |
|---|---|---|
| 仓库副本 | 读知识库、改 `production_strategies/`、写回测、写结论卡 | — |
| 东财客户端 + 既有 `_upload_chip_*.py` / 批次目录 | 按铁律拉筹码、校验、上传 | 用 `pull_chip_from_kline.py` 顶替真实 CYQ |
| 上海机 SSH（用户已配好、且明确让你连） | 查 `data_readiness` / 日志 / 覆盖率 | 把密钥写进聊天或仓库 |
| QMT / 通达信 | 无。最多告诉用户「从哪个文件复制到哪」 | **禁止**直接写交易端目录 |
| `C:\alphapilot\` 实盘日志 | 无则不要编造成交；让用户给路径或让主电脑 Cursor 查 | 用过期本地缓存当生产真相 |

**撞车规则：**

- 同一交易日不要两个人同时改同一份 `production_strategies/track_*` 文件。动手前看 `CHANGELOG.md` 最新一条 + checkpoints 最上几行。
- 改完立刻写 CHANGELOG + checkpoint，并在回复用户时写清「改了哪一层、要不要部署」。
- 日常验证：**PASS 静默，FAIL 才报**。不要每天发「今日已通过」长报告。
- 服务器数据真相以 **SSH 上海机闸门**为准，不以本机过期文件为准。

---

## 4. 硬规则（违反会出事）

### 4.1 筹码（08-24 半截上传事故）

生产 chip **只认你上传的东财真实 CYQ**。

- 批次不连续、覆盖 <4850、日期不对 → **禁止上传**。先补拉再校验。
- 校验：`python scripts/check_chip_batches.py --date YYYYMMDD`（本地副本也在 `production_strategies/server/check_chip_batches.py`）。
- 当天补不齐：**宁可不传**（服务器留昨天全量，闸门会告警），也不许传半截，更不许用 K 线推演筹码覆盖。
- 建议 17:30 前传完，好让 18:15 `daily_coverage_check` 兜住。

### 4.2 K 线

判定用 `amount / (volume × close)`：≈1 = 已是股（别动）；≈100 = 手（×100 转股）。禁止只看列名。

**WorkBuddy：K 线只读不写。** 写入归 cron `15 16 * * 1-5` 的 `fix_kline_server.py`。

### 4.3 生产代码

- **只改** `production_strategies/`。根目录同名 `qmt_model_*.py` / `track_b_*.py` / `tdx_full_chain.py` / `export_qmt_scores.py` **冻结**。
- 每次改必须追加 `production_strategies/CHANGELOG.md`（插在最新一条上面）。
- QMT 文件必须 **纯 ASCII**（中文注释会在 QMT 加密后 `SyntaxError`）。改完跑：

```bash
python -c "import ast,pathlib; p=pathlib.Path(r'文件路径'); b=p.read_bytes(); b.decode('ascii'); ast.parse(b.decode('ascii'))"
```

TDX 允许 UTF-8 中文注释。sim 与 live 逻辑必须同步，差异只允许 CONFIG。

- **禁止**直接写 QMT python 目录 / TDX `PYPlugins\user`。告知用户部署即可。
- 改选股/卖出逻辑才升版本号；只改配置/注释不升版本。
- `rd_workshop/` 与生产互相只读，**禁止**自动把实验模型热切换进生产。

### 4.4 不要动的已知保留项

- **F3**：拒单后 `sent_today` 阻止重试——用户明确保留，不要改。
- 网页融合排名 **不要**前移进 `candidates.json`（已否决）。
- Dual Thrust **不适合 A 股**（已否决）。
- 生产仓位维持 **最多 4 只 × 20%**，不要改成 3×30%（2026-09-02 回测否决）。
- 同花顺涨停/热股/龙虎榜 **不进** 09:35 打分 / P2 排序。

---

## 5. 一天里谁在跑（你对表用）

工作日大致时钟（上海）：

| 时刻 | 谁 | 做什么 |
|---|---|---|
| 00:30 / 01:30 / 02:30 | 服务器 | 预检 `preflight_checkpoint.py` |
| 04:40 | 服务器 | 两融 / 预告等 T+1 补拉 |
| 04:50 | 服务器 | `data_readiness_gate`（chip 最新日覆盖 ≥95% 才 ready） |
| 05:00 | 服务器 | `alphapilot_pipeline_v3.py` 主管线 |
| 06:30 | 服务器 | `export_qmt_scores.py --fullpool` → 轨道 B 兜底池 |
| 09:33 | 服务器 | `market_tone`（A50+CNH，只收紧资金门，不改打分） |
| 09:35 | 服务器 | scanner 双路径 + `morning_live_fund_select` 终选 |
| 09:36 | 服务器 | 导出 `{date}.candidates.json`（轨道 A 买卖端只读这份） |
| 09:38 | 服务器 | 三路融合 Top10 = **网页展示**，不是下单序 |
| 09:35–14:57 | QMT/TDX | 买卖模型逐 bar |
| 16:15 | 服务器 | `fix_kline_server` + 融合 IC `run_feedback_loop` |
| 16:25 / 16:26 | 服务器 | T+N 累计 / shadow Top2 报告 |
| 17:00 | 服务器 | RD `feedback_auto_tune`（错开 16:15，避免抢 K 线） |
| ~17:30 前 | **你** | 筹码拉全 → 校验 → 上传 |
| 18:15 | 服务器 | 全数据覆盖复查 |
| 21:30 | 服务器 | V25 重训（AUC 门拒绝 = 保护旧模型，不是「重训失败」） |
| 22:20 | 服务器 | 换手因子 shadow（观察中，未晋升） |

09:35 scanner：**池 ≥100** 池内 0.6 管线 + 0.4 动量重排；**池 <100** 涨幅 Top~1000 资金轨。弱市仍启用。禁止擅自删 Top1000 分支。

---

## 6. 2026-09-02 现场快照（接手前先知道）

以 `knowledge/ops/checkpoints.md` 和 `production_strategies/CHANGELOG.md` 最新条为准。写本文时：

**买卖模型（权威代码已改，交易端多半还没部署）：**

- 轨道 A：只让 `candidates.json` **rank 1–2** 进 P2（`MAX_CAND_RANK=2`）；满仓 **关掉 rotation**；仓位 **4×20%**。
- `vwap_weak_early`：**二次确认**。09:35–09:50 第一次仍低于昨 VWAP 只记、打 `[VWAP] first confirm wait 2nd`，**不卖**；同一分钟轮询不算第二次；下一分钟仍低才卖。涨回昨 VWAP 则撤销。
- 起因：QMT 实盘 **300475 香农芯创** 09-02 09:36 第一跳卖在当日最低附近。
- **`t2_force` / `wyckoff_bc` 仍是窗口第一跳就卖**，不要一起改成二次确认。
- 权威版本（部署后 INIT 应看到）：A QMT live `v2.30-tpl` / sim `v2.30` / TDX `v2.29`；B QMT `v2.7-tpl` / `v2.7` / TDX `v1.18`。若用户还没部署，实盘可能仍是更旧 INIT。
- `_hold_days` 已改 **交易日** 计数（周五买周一 = T+1，不是日历 3 天）。

**选股模型：**

- 生产打分 = V25 **106 维** 三模型集成。模型文件日期和「数据是否就绪」是两件事。
- 融合 IC（16:15）调网页三路权重，**不是** QMT 下单序。
- 08-31 重训曾被 AUC 门拒绝（保护旧模型），属正常。

**数据：**

- 09-02 凌晨预检曾全绿；K 线 / 筹码 / 资金流对齐上一交易日即可，龙虎榜/两融常为 T+1。
- `data_readiness.json` 若还是昨天 09:35 快照，04:50 前可能正常，不要当故障。

**加密纸盘（新加坡）是另一条线。** 用户没点名不要掺进 A 股任务。

---

## 7. 适合你分担的工作（用户没指定时按此挑）

**很适合你（尤其另一台电脑）：**

- 交易日筹码：拉全 → `check_chip_batches` → 上传（仅当本机有东财链路）。
- 交叉验证：复现 Cursor 刚做的回测数字，找口径错。
- 只读核查：checkpoints 里「待盯」项、覆盖率、INIT 版本是否已部署。
- `bt_research/` / `rd_workshop/` 实验（不碰生产 cron、不晋升模型）。
- 知识库回写、决策卡、和 Cursor 的同步稿（入 `knowledge/decisions/`）。

**要先对齐再做：**

- 改 `production_strategies/` 买卖逻辑（必须 CHANGELOG + ASCII + 告知部署）。
- 改服务器选股脚本（改完是选股层，不要顺手改 QMT）。

**不要做：**

- 直接部署 QMT/TDX；改根目录冻结快照；写 K 线缓存；用推演筹码覆盖生产。
- 把网页 Top10 当成实盘买入列表。
- 未确认本机有密钥就「连一下服务器改 cron」。
- 每天 PASS 日报。

---

## 8. 结论怎么写回去

重要结论（回测数字、否决、数据源事实、设计决策）必须落盘，否则下一端看不见。

1. **全局 inbox**（有则写）：`C:\Users\elvisq\knowledge\inbox\YYYY-MM-DD-短横线描述.md`  
   模板：`C:\Users\elvisq\knowledge\inbox\_TEMPLATE.md`  
   frontmatter 必填：`project` / `domain` / `title` / `date` / `status` / `tags`  
   `domain`：`architecture` | `crypto` | `strategy` | `data` | `qmt` | `marketing` | `other`
2. 与本项目相关 → 同步 `knowledge/` 对应档案，必要时改 `knowledge/INDEX.md`。
3. 可复查的改动 → `knowledge/ops/checkpoints.md` **对应表最上面加一行**。层只能是：选股模型 / 买卖模型 / 数据 / 文档。
4. 改了生产策略 → `production_strategies/CHANGELOG.md`。
5. 和 Cursor 的分工共识 → `knowledge/decisions/` + `MEMORY.md`（只写稳定规则）。

---

## 9. Suggested skills

按你接到的任务选用（有 skill 文件就先读再干，不要凭通用编程习惯改框架）：

| 场景 | 先读 |
|---|---|
| 用户说调研 / 全网搜 / 看看大家怎么评价 | 本机若有 `agent-reach` skill，先走它 |
| 用户贴截图 / 报错图 / 盘面 | `docs/WORKBUDDY_VISION_BRIDGE.md`；有 vision-bridge 则先转文字再答 |
| A 股行情 / 财务 / 选股筛选（查询，不是改生产） | 若已装万得 / fuyao MCP，用数据工具，不要用过期缓存编数 |
| 用户要落地代码、按规格实现 | 先对齐 `AGENT_RULES.md`；有 `implement` / `tdd` skill 则按它的缝来 |
| 用户要拷问方案 / 先把决策问清 | grilling / grill-with-docs |
| 会话要结束、留给下一端 | 再写一份短交接，指回 `checkpoints.md`，不要复制本文 |

没有对应 skill 就按本文 + `AGENTS.md` 做。

---

## 10. 接到任务后的回复模板

对用户说话时标明层，例如：

> 这是 **买卖模型** 问题，不是选股。权威文件在 `production_strategies/track_a/...`。我改完会写 CHANGELOG；**需要你手动部署** QMT 实盘/模拟。服务器选股不用动。

不要说「策略改好了」这种混层句。

---

## 11. 第一轮自检清单（读完本文后勾）

- [ ] 仓库已打开，能读到 `AGENTS.md` 和 `production_strategies/CHANGELOG.md` 最新条
- [ ] 已扫 `checkpoints.md` 最上「待盯」：当前最重要的是 **vwap 二次确认等用户部署**
- [ ] 知道本机有没有东财上传能力；没有就不要接「今天传筹码」
- [ ] 知道生产模型是 106 维，不是 116
- [ ] 知道网页 Top10 ≠ QMT 买入名单
- [ ] 准备好：PASS 不吵、FAIL 才报

读完后用三句话向用户确认：「我是新 WorkBuddy；已读交接；今天先做 ___（等你指定）。」

---

## 12. PC → MacBook 迁机（2026-09-05）

若用户是在把研发环境迁到 Mac，**先读**仓库内：

`knowledge/ops/macbook-migration-checklist.md`

要点：PC 原样保留不删；经 Git 同步代码；大数据按需从服务器/新加坡备份拉；QMT 仍在 Windows。  
不要用 Cursor Cloud「Include uncommitted changes」当迁机手段。
