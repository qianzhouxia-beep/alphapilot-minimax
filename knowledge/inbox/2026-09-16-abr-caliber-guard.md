---
project: alphapilot
domain: strategy
title: abr 口径护栏——非标定源（L1）不再硬弃（A v2.49 / B v2.20）
date: 2026-09-16
status: decision
tags: [track-a, track-b, abr, skip_low_abr, caliber, sim-only]
---

# abr 口径护栏（2026-09-16）

## 问题
A 轨连续空单，WB 诊断实锤头号弃票门 = `skip_low_abr`（000722 等）。
根因不是「abr 门本身错」，而是 **口径错配**：
- `MIN_ACTIVE_BUY=0.52` 由 `BT_ABR_GATE_REPORT.md` 的 `P2_cum_052` 标定 —— **全日累计 TDX/mootdx 逐笔**口径；
- 但 mootdx feed 缺位时回退 **QMT L1 末 120 笔近似**（`_get_active_buy_ratio`），这是**第三种口径**；
- 把 0.52 施加在 L1 近似值上 ⇒ 系统性误弃。

## 决策（最小、可辩护）
1. **只在标定口径（src=mootdx）保留 0.52 硬卡**。
2. `src=l1` 且低于 0.52 → **fail-open**（不否决；不因未标定口径弃票）。
3. **值域护栏**：abr ∉ [0,1] 或非有限（NaN）→ 视同缺失 → fail-open。
4. **不重标定 0.52、不关掉 abr**：阈值与「mootdx 口径硬判」语义未变；重标定需同口径回测（E20）另议。

## 落地
| 轨 | 版本 | 落点 |
|---|---|---|
| A | v2.49 | `_p2_decide` abr 段 |
| B | v2.20 | `_p2_gate`（逐 bar 硬重判）+ `_p2_decide` 两处 |

新增 `ABR_CALIBRATED_SRC_ONLY=True` / `_abr_in_range()` / `_abr_verdict()`。
日志：`[P2] abr out-of-range -> fail-open` / `[P2] abr uncalibrated -> fail-open`；B gate notes `abr=oob_open` / `abr=uncal_open`。

## 验证
- A `_ut_abr_caliber_v249` 12/12；B `_ut_abr_caliber_v220` 9/9（含 `ABR_CALIBRATED_SRC_ONLY=False` 回退旧行为）。
- ASCII + AST + CRLF；md5 A=`4ddcc871…` / B=`7a789479…`。

## 待现场
`C:\alphapilot\l2_feed\{date}.json` 是否存在/新鲜，决定 feed 是走 mootdx 还是 L1（WB 规格 §8.5，仍未核）。

---

## 追加（2026-09-16 晚，同版本，日志级）——窗口口径残留 + `win=N` 证据

WB（评论 `5695430096`）指出：护栏只修了「L1 vs feed 的**源**混用」，**没修 feed 自身的窗口口径**。核查属实，且更糟：

- `tencent_tick_feed.py`（09-15 起替代 mootdx）的 abr = **末 800 笔滚动窗**（`MAX_TICKS=800`，`_compute_abr` 取 `buffer[-800:]`）；
- 而 `0.52` 标定于 `P2_cum` **全日累计窗**；
- 原 v2.49/v2.20 注释还写着「feed = 全日累计 = P2_cum」——那是**旧 mootdx 生产者**的性质，换源后**已失真**（文档错）。
- `deliver/DELIVERY_tencent_tick_feed.md` 亦自认「0.52 为 TDX 口径标定、同日 TDX↔腾讯对照未做」。

**处置（刻意不重标定，E20/E29）**：无同日 TDX↔腾讯对照 ⇒ 不拍数、不动 0.52；只补可直接用的审计证据：

1. feed 读取器额外返回 `n`（变量 `win`）；P2 abr 日志补 `src=feed win=800`；A 记 `item["abr_win"]`、B 记 `it["abr_win"]`（pass 情形也有值）。
2. 标定源标签 `"mootdx"` → 常量 `ABR_CALIBRATED_SRC="feed"`（读的是**文件**，与生产者无关）。
3. 注释如实描述窗口口径，并标注 E20 残留（供 E23 复验与未来重标定）。

**同版本覆盖**（A v2.49 / B v2.20；日志级，规则 6 不升版；未部署故直接并入）。验证：单测 18/18、11/11；pyflakes 无新增未定义名；md5 A=`1be520f9544daa3286273ee35b794c22` / B=`4ee750c73d1c58c348a0285505bd86de`（**取代上文旧 md5**）。

**仍待现场**：feed JSON 的 key 必须与 QMT `code` 串完全一致（如 `002218.SZ`）；若用裸码会 `data.get(code)` miss → 静默回退 L1。一条 `findstr 002218 C:\alphapilot\l2_feed\{date}.json` 即可核。

