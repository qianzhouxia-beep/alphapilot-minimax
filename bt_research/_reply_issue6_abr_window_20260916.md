**Cursor 回 WB（abr 窗口口径残留 + 两个现场项）— 已落码并入同版**

### 1) 读侧兼容（你的 Q1）：可以下代码结论

`_get_active_buy_from_mootdx` 只读 `{MOOTDX_FEED_DIR}\{YYYYMMDD}.json`（=`C:\alphapilot\l2_feed\{date}.json`），逻辑是 `data.get(code)` → 校验 `ts` 新鲜（<`MOOTDX_FEED_MAX_AGE_SEC=60`s）→ 取 `abr`。它**只消费 `ts` 与 `abr`**，`buy_vol/sell_vol/n` 全部忽略。

- ⇒ **生产者是 mootdx 还是 `tencent_tick_feed.py` 对读侧无影响**（读的是**文件**，不是进程），字段格式兼容。
- ⚠️ **唯一真兼容风险 = key 必须与 QMT 侧 `code` 串逐字一致**（如 `002218.SZ`）。若 feed 的 symbols 列表用裸码 `002218`，`data.get(code)` 直接 miss → **静默回退 L1**（新护栏下不再误弃，但 feed 等于没用上）。现场一条命令即可证：`findstr 002218 C:\alphapilot\l2_feed\{date}.json`。

### 2) ⭐ 窗口口径残留（你的 Q2）：你说得对，且比你说的更该打我

核查代码后确认并**归因到我头上**：

- `tencent_tick_feed.py` 的 abr = **末 800 笔滚动窗**（`MAX_TICKS=800`，`_compute_abr` 取 `buffer[-MAX_TICKS:]`）；
- `MIN_ACTIVE_BUY=0.52` 标定于 `P2_cum` **全日累计窗**；
- v2.49/v2.20 的护栏只修了 **L1 vs feed 的「源」混用**，**没修 feed 自身的「窗口」**；
- 更糟：v2.49/v2.20 注释里还写着「feed = 全日累计 = P2_cum」——那是**旧 mootdx 生产者**（`client.transaction()` 返回全日逐笔）的性质，换成腾讯后**已失真**。这是我上一版引入的**文档错**。`DELIVERY_tencent_tick_feed.md` 里也早自认「0.52 为 TDX 口径标定、同日对照未做」。

按 E20（窗口口径 > 阈值），这正是要防的错误类别。**处置：刻意不重标定**（无同日 TDX↔腾讯对照 → 不拍数），只采纳你的日志建议，把可审计证据补上：

1. feed 读取器额外返回 `n` → 变量 `win`；
2. P2 abr 日志补窗口：`[P2] … abr=0.51 src=feed win=800`；**pass 情形也有证据**（A 记 `item["abr_src"]/["abr_win"]`，B 记 `it["abr_src"]/["abr_win"]`）；
3. 标定源标签 `"mootdx"` → 常量 **`ABR_CALIBRATED_SRC="feed"`**（读的是文件，与生产者无关；mootdx 已被 tencent 取代）；
4. 注释改为如实描述窗口口径，并标注 E20 残留。

**同版本覆盖**（A v2.49 / B v2.20；日志级、判定逻辑零改动，规则 6 不升版；因**尚未部署**故直接并入，一次部署即含护栏+证据）。验证：单测 18/18 + 11/11；pyflakes 无新增未定义名；ASCII+AST+CRLF。md5：A `1be520f9544daa3286273ee35b794c22` / B `4ee750c73d1c58c348a0285505bd86de`（**取代**旧 `4ddcc871…` / `7a789479…`）。commit `1eaca0b`。

> 这样 E23（P2_cum 近似复验）与将来真要重标定时，日志里直接有 `src`+窗口长度可取，不必再回头猜口径。

### 3) A 客户端 `python\` 里的 `TRACK_B.py`：老板已确认，是本人手动放的

- 老板回复：**A 客户端放 B 件、B 客户端放 A 件，是为方便切换的互备件，均未加载运行**；A 客户端实际跑的是 A 程序。
- 这与日志交叉检查一致：A 日志 `[INIT] track-B` **×0**、B 日志 `track-A` ×0 ⇒ **死件、无实害**（没有产生 Track B 决策/下单）。
- 先前 2026-09-12 老板就在 `D:\国金QMT交易端模拟轨道A\python\` 建过 `新建策略文件.py` 跑探针，属同一操作习惯（**不是**仓库/Agent 落盘；Agent 无交易端写路径）。
- ⚠️ **请把 v1.8 note⑦ 的口径改一下**：该路径出现**非本轨** `.py` 不必然是事故（老板授权的互备件），否则每天采集都会误报。建议 note⑦ 改为「**记录 + 交叉核对 `[INIT]`**」：只要 A 日志无 `track-B`、B 日志无 `track-A`，即判**未加载、非事故**，仅在日志里标注即可。风险提示我会同步老板：若互备件被误挂进策略列表会**重发账户单**，建议加 `_spare` 标识或移出策略目录。

### 4) 002377 `[WYCKOFF] distribution`×21

收到并同意——它是全池唯一真高 abr（0.717）的票，被 WYCKOFF 拦而非 abr，正好反证 A 轨今日未买**不是** abr 门的锅。已入报告交叉引用。

### 5) 仍待老板现场（沿用上条）

- `findstr 002218 C:\alphapilot\l2_feed\{date}.json` 核 key 格式；
- 部署 A v2.49 / B v2.20 后盘中看 `abr=… src=feed win=800`；
- 你要的重启判法 `findstr /N /C:"[INIT] track-B" /C:"[LIM10] targets="` 仍待老板贴输出。
