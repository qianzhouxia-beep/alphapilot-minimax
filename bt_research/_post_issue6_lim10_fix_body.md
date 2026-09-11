## 【Fix A 已实现 · 待部署】Track B LIM10 fail-open → fail-safe（Cursor 09-12 02:2x）

按 `issuecomment-5634114857`（P0 核验）+ `issuecomment-5634160271`（Fix A 放行）实施。**Fix A 已在仓库落地并推 `fe8f751`；Fix C 未做（按授权另单）**。以下交付三件 + 边界说明。

---

### 一、交付 ①：diff（`track_b/TrackB_track_b_qmt_auction_sim.py` v2.12 → v2.13）

```diff
@@ _check_buy：path_fade/loud_vol 过滤之后
+    # v2.13 P0 fail-open fix: in live-pool mode, buying is allowed ONLY from
+    # money_pass names (v2.8 spec: "No fallback fill"). If the money gate
+    # rejects every row, the old code fell through to the else branch and
+    # bought server-rejected names. Fail-safe: go flat for the day.
+    if (LIM10_ENABLE and bool(getattr(C, "live_pool_active", False))
+            and not money_items):
+        if not getattr(C, "_lim10_flat_logged", False):
+            C._lim10_flat_logged = True
+            print("[LIM10] money_pass all rejected -> flat (no fallback) "
+                  "other=" + str(len(other_items)), flush=True)
+        return
     lim10_ok = (LIM10_ENABLE and bool(getattr(C, "live_pool_active", False))
                 and any(it.get("limit_cnt_10d") is not None for it in money_items))
```

```diff
@@ else 分支（原 L2834 误导文案）
-                print("[LIM10] no limit_cnt_10d on pool -> FCFS fallback", flush=True)
+                # v2.13: reached only when money_items is non-empty but every
+                # row lacks limit_cnt_10d (spec-exempt FCFS). The all-rejected
+                # case returns earlier; wording no longer misreports it.
+                print("[LIM10] money_pass present but limit_cnt_10d missing "
+                      "-> FCFS fallback", flush=True)
```

版本串/注释同步 v2.13（`[INIT] track-B v2.13 (LIM10-failsafe+...)`）。**纯 ASCII，未触碰 live 模板 / track_a / 服务器选股端。**

### 二、交付 ②：Fix D 回归用例（`_test_lim10_failopen.py`，先写后改）

**改前（A 红，P0 复现）**：

```
== A. P0 repro: live pool, money gate rejects ALL -> 0 buys ==
[LIVE] server rerank pool n=3 money_pass=0
[LIM10] no limit_cnt_10d on pool -> FCFS fallback      <-- 误导文案实锤
[BUY] 300001.SZ x440000 @ 10.0 track-B auction rank=1 fallback
[BUY] 300002.SZ x440000 @ 10.0 track-B auction rank=2 fallback
  [FAIL] A money_pass all False -> no buy (fail-safe) buys=['300001.SZ','300002.SZ']
  [PASS] B classic fallback still buys
  [PASS] C limit_cnt_10d missing -> FCFS still buys
===== 2 passed, 1 failed =====
```

**改后（3/3 绿）**：

```
== A. P0 repro: live pool, money gate rejects ALL -> 0 buys ==
[LIVE] server rerank pool n=3 money_pass=0
[LIM10] money_pass all rejected -> flat (no fallback) other=3
  [PASS] A money_pass all False -> no buy (fail-safe) buys=[]
== B. classic pool -> fallback still allowed ==
  [PASS] B classic fallback still buys buys=['300001.SZ','300002.SZ']
== C. live pool, money_pass present but limit_cnt_10d missing -> old FCFS ==
[LIM10] money_pass present but limit_cnt_10d missing -> FCFS fallback
  [PASS] C limit_cnt_10d missing -> FCFS still buys buys=['300001.SZ','300002.SZ']
===== 3 passed, 0 failed =====
```

三条断言对应你的放行条件 §三(2)：A=全否决池买入 0（改前先红）；B=classic 池 fallback 不误伤；C=3b（有 money_pass 但 `limit_cnt_10d` 全缺）仍走旧 FCFS。

### 三、交付 ③：当日回放买入笔数对照（`20260911.fullpool_live.json`，我直接从 nginx 取的原文）

| 项 | 值 |
|---|---|
| 池 n / asof | **32** / 2026-09-11 09:36:14 |
| `money_flow_pass` | **True 0 / False 32** |
| `limit_cnt_10d` 非空 | 31/32 |
| fallback 合格名单（rank≤15 且非 `fund_hard_fail`） | **15 只** |
| **改前** 实际成交 | **2 只**：`300061`(rank 6)、`002893`(rank 12) |
| **改后** | **0 只（空仓）** |

即：修复后 09-11 当日 Track B sim **一笔都不买**，与你"这两只只有 bug 路径解释得通"的判定一致。

### 四、边界与状态（对应你的放行条件）

- **条件 ①（部署件行级 diff/hash）**：本仓库 `track_b/TrackB_track_b_qmt_auction_sim.py` 改前 md5 = `3a8c4b9ca4284c80ee549144016a2549`、改后 = `1da96de8636cb9b5f014bda1ad8812ef`。**Windows QMT 部署件我这边访问不到**，需老板核对改前 md5 是否与部署件一致；不一致则以运行时文件为准再核（纪律 #9）。
- **条件 ③（文案）**：新分支打印 `money_pass all rejected -> flat (no fallback)`；旧误导串已改。**⚠️ 一处按项目规约做了 ASCII 化**：QMT 文件必须纯 ASCII（非 ASCII 会触发 QMT 加密 `SyntaxError`），故用英文串而非"money_pass 全灭 ⇒ 空仓"，语义等价。
- **Fix C（`passorder` 后不校验委托/成交回报 → 幽灵账）**：**未做**，按授权独立 commit/ticket。需要我起新帖/新分支时请点名。
- **部署**：Fix A 目前只在仓库；**需老板复制 v2.13 到 Windows QMT 模拟盘目录**。实盘模板未动。sim 满 1 日核对前不进 live。

### 五、关于 G1 扩窗 [85]/[86]

收到你"不预设接受、先独立复现"的处理，无异议。关于 regime 切点 08-19（问题 1）：该切点**不是拟合出来的**，来自 `market_env.weak_regime` 的状态翻转（09-08 前 weak=False、08-20 起 weak=True 的口径附近），我可以在你复现后，按你给的替代切点（如按指数均线/等分位）重跑一版做敏感性。问题 2 请在你复现连上后一并给出，我再答。

—— Cursor
