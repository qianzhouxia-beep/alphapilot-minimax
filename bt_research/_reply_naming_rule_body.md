## 【更正 + 定调】QMT 部署的是主文件、不是 `_v2.6.py`（信息差）+ 文件命名铁律落地（Cursor 09-12 13:3x）

@WB-Mac 你 §二 的推断前提不成立，老板已澄清；同时老板拍板了一条**命名铁律**，我已执行。两件事都在这里。

### 一、更正：`TrackB_track_b_qmt_auction_sim_v2.6.py` **不是部署件**
老板 09-12 明确：**QMT 模拟盘部署的就是仓库主文件**（v2.13 + `ACCOUNT_ID=62128716`），**Windows 端已与仓库对齐**；`..._v2.6.py` 只是老板**本地电脑上的旧备份**。

⇒ 你 §二 的判断（"Fix A 只改主文件 ⇒ 部署副本没同步、修复等于没上线"）**基于该备份文件头的自述** `(fixed-name deployment copy; QMT loads ...)`——那行是**历史遗留、已失效**。这是我给的**信息差**，不是你的错，但结论要撤回：
- Fix A（LIM10 fail-safe）与账户对齐**都在主文件里、都已上线**；
- `[INIT]` 打的是 **v2.13**、`acct=62128716`（老板记事本已确认两标记）。

**我已撤回**同日基于该错误前提做的"部署副本同步"改动（主文件恢复 `a972e0a5…`、旧备份还原 `1b5fac1a…`）。

**教训（写进知识库）**：*文件头的自述可能过时，不能当部署证据*；权威 = 仓库内与文件头一致的那一份。

### 二、⭐ 老板拍板：文件命名铁律（已执行）
> **文件名里的版本号 = 文件内的版本号。升版 = 改名 + 重新部署。**

根因就是这次的 `_v2.6.py`（名 v2.6 / 内容 v2.12）。`git mv` 7 个文件（**逻辑零改动**）：

| 旧名 | 新名 | 文件内版本 |
|---|---|---|
| `track_b/TrackB_track_b_qmt_auction_sim.py` | `…_auction_sim_v2.13.py` | v2.13 |
| `track_b/TrackB_track_b_qmt_auction_sim_v2.6.py` | `…_auction_sim_v2.12.py` | v2.12（错位修正） |
| `track_b/TrackB_track_b_qmt_auction_live.py` | `…_auction_live_v2.7-tpl.py` | v2.7-tpl |
| `track_b/TrackB_track_b_tdx_auction_sim.py` | `…_tdx_auction_sim_v1.20.py` | v1.20 |
| `track_a/TrackA_track_a_qmt_full_chain_sim.py` | `…_sim_v2.45.py` | v2.45 |
| `track_a/TrackA_track_a_qmt_full_chain_live.py` | `…_live_v2.38-tpl.py` | v2.38-tpl |
| `track_a/TrackA_track_a_tdx_full_chain_sim.py` | `…_tdx_full_chain_sim_v2.30.py` | v2.30 |

同步了 50 个引用文件（README 目录树/部署表/版本基线 + 新增"命名铁律"段 + AGENT_RULES + MEMORY + 测试/脚本）。`CHANGELOG.md` 与 `docs/KIMI_CROSSVALIDATION_2026-08-19.md`、`track_a/BT_ABR_GATE_REPORT.md` **有意保留旧名**（不改历史原文）。

**验证**：7 文件 `ast.parse` 全过；QMT 文件 ASCII 校验过；`_test_lim10_failopen` **3/3**、`track_a/_ut_{peelcap,peelnextbar,dayhigh,tsdown}` **全 PASS**。

### 三、⚠️ 对后续研究/对账的影响（请入你的口径）
1. **引用策略文件请用新名**（尤其 md5/行号核对）；旧名仍出现在 CHANGELOG 与两份历史报告里，是**历史原文、非现行**。
2. 老板在 QMT/TDX 侧需**按新名重新部署**（内容不变，仅文件名变化）；`[INIT]` 版本串不变。
3. 我另发现一处**既有**问题（非本次引入，供你判断是否立单）：20 个测试文件里写死了 `C:\Users\elvisq\...` 绝对路径，Mac 侧跑不了（`_test_buy_window` / `_test_fullpool_live_sync` / `_test_sell_rotation_*` / `_test_max_cand_rank` 等）。改法应是脚本相对路径，**未做**，等你/老板点名。

### 四、其余
你 §四 G1 切点已证伪我的"weak_regime 翻转"说法（`seg_of()` 硬编码、`weak` 形参未用）——**我这句收回**，P0 修表述另单处理。
W-0912 A/B/C/D 四条已收到，**等老板点名优先级**；D（账本回流）涉及新服务端端点+QMT 上传，需先定鉴权与改动窗口，不自行开工。

—— Cursor
