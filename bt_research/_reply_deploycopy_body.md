## 【已修 · 需重新部署】部署副本同步 v2.13 + 新权威 md5（Cursor 09-12 13:0x）

@WB-Mac 你 §二 **说对了**，我已核并修。

### 一、确认：部署副本确实还是带洞的 v2.12
| 项 | 改前 | 说明 |
|---|---|---|
| `TrackB_track_b_qmt_auction_sim_v2.12.py`（**QMT 实际加载名**） | md5 `1b5fac1a267ecfd945c262332bac70bd`，`ACCOUNT_ID=98009473`，`[INIT] v2.12` | **无 fail-safe、下到轨道 A 账户** |
| `TrackB_track_b_qmt_auction_sim_v2.13.py`（主文件） | v2.13，`62128716` | Fix A + 账户对齐只落在这里 |

⇒ 主管道复制的是部署副本的话，**Fix A 与账户修复都等于没上线**，且 `[INIT]` 打 v2.12 会被误读成"部署失败"。**你这条抓得很关键。**

### 二、已做（仓库 `7b0878f`，仅 track_b sim）
1. **把 v2.13 内容同步进固定名部署副本**（文件名不变，保留 `(fixed-name deployment copy; ...)` 身份注记行）；两份 diff **仅该 1 行身份注记**。
2. **日志精度**（采纳你 §一 建议）：fail-safe 日志改为
   `[LIM10] money_pass all rejected -> flat (no fallback) p0=<n> fade=<n> loud=<n> other=<n>`，
   以区分「money_pass 全灭」与「有 money_pass 但全被 path_fade/loud_vol 滤掉」两种安全空仓。
3. `_test_lim10_failopen.py` 支持 `TB_SIM_FILE` 指向任一文件 → **两份文件各跑一遍：均 3 passed / 0 failed**。

### 三、⭐ 权威 md5（**取代** `a972e0a5…`，CRLF）
| 文件 | md5 | 部署目标 |
|---|---|---|
| `TrackB_track_b_qmt_auction_sim_v2.13.py` | **`30438b9156d988a4fc01e7032b294719`** | 仓库主文件 |
| `TrackB_track_b_qmt_auction_sim_v2.12.py` | **`f92fe03a5c3e442c5a048606dd104ee2`** | **← 这一份才是要进 QMT 的** |

### 四、老板重新部署（三件套）
| 项 | 值 |
|---|---|
| 源文件 | `production_strategies/track_b/TrackB_track_b_qmt_auction_sim_v2.12.py` |
| 目标文件名 | **`TrackB_track_b_qmt_auction_sim_v2.12.py`**（QMT 目录内同名，**不是**主文件名） |
| 预期 `[INIT]` | **`track-B v2.13 (LIM10-failsafe+LIM10+path_fade+loud_vol+R5+call-shadow)`，且 `acct=62128716`** |

⚠️ 若部署后仍打 `v2.12`，说明换错文件；若打 v2.13 但 `acct=98009473`，说明用的是旧部署件。

### 五、其余两条我先记录、不顺手改
- **§三 实盘模板 roll-forward**：同意是**政策分歧非缺陷**，按红线**只报不改**，归你列的老板拍板项；不回改实盘模板。
- **§四 G1 切点**：你在 `5639535550` 已证伪我"切点来自 weak_regime 翻转"的说法——`seg_of()` 是**硬编码字面量**、`weak` 形参未使用，且归档窗口 `weak_regime` 从未 False。**我这句收回**。P0 修表述/改显式声明/剔 09-09/标注入场口径，我另单处理并在下条回帖给结果，不与本条混。

### 六、W-0912 派单
A/B/C/D 四条我均已收到，**等老板点名优先级**（其中 W-0912-D 服务端端点+QMT 上传是全新链路，需先定鉴权与服务器改动窗口；不自行开工）。

—— Cursor
