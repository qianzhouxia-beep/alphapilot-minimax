---
project: alphapilot
domain: data
title: 5m K线历史回补方案（baostock, ≥6个月）
date: 2026-09-11
status: conclusion
tags: [kline5m, baostock, data-backfill, firstboard, entry-timing]
---

# 5m K 线历史回补方案（baostock）

## 背景
`data/kline5m/` 由 `build_kline5m.py` 每日 16:20 用 **mootdx** 增量累积；mootdx 只能回溯 7 天，
因此历史库是从 2026-07-23 开始「攒」出来的，截至 09-11 仅 **34~35 天**（4991 只，每只 ~1680 根）。
首板 hold 决策的落地②要求把 5m 补到 **≥6 个月**。

## 结论：baostock 是合适的长历史 5m 源
实测 `data/kline5m/000001.parquet` 与 baostock 在重叠日 2026-07-23：

| 标的 | 重叠 bar | close 最大差 | amount 相对差(中位) | amount/(vol×close) |
|---|---|---|---|---|
| 600519 | 48 | 0.0000 | 0.00000 | 0.9999 |
| 000001 | 48 | 0.0200 | 0.00679 | 1.0001 |
| 300750 | 48 | 0.2800 | 0.00618 | 0.9997 |

口径对齐要点：
- `query_history_k_data_plus(..., frequency="5", adjustflag="3")` → **不复权**，与 cache 一致
- **volume 单位 = 股**（非手）→ 与 cache 的 `vol` 一致（`amount/(vol×close)≈1.0`）
- bar 时间戳 **09:35..15:00**（收盘标价）→ 与 cache 相同
- 输出列映射到 `open,close,high,low,vol,amount,year,month,day,hour,minute,datetime,volume,symbol`

## 落地方式
脚本：`bt_research/backfill_kline5m_baostock.py`（服务器同名根目录）
- **只新增 `datetime < 现有最早 bar`**，绝不改写/删除现有行（生产 cache 保护）
- 原子写（`.tmp` + `os.replace`）；单只失败不中断
- 幂等：现有最早 bar ≤ start+7d 即跳过（可断点续跑）
- **16:18–16:28 避让 build_kline5m（16:20 cron 会并发写同一批文件）**
- 实测速度 ~5.7s/只（单进程）；`--shard i/N` 4 进程并行 → ~3s/只/片 → 全量 ~1h

## 其他源评估
- **东财 min hist**（`stock_zh_a_hist_min_em` / `push2his`）：服务器直连被断（`RemoteDisconnected` / SSL EOF），不可用
- **腾讯 gtimg**：WAF 501 会封 IP（见 kline-fallback-sources 卡），不适合批量长历史
- **westock**：单位不统一（688=股、其余=手），仅备选
- **mootdx/TDX**：只能 7 天

## 用途
G1 影子、首板 setup 的入场/出场 5m 仿真、入场分钟衰减（09:36 窗口）复算。

## 关联
- `bt_research/bt_firstboard_lift3.py` · inbox `2026-09-10-firstboard-lift.md`（hold 决策）
- 服务器日志 `output/logs/backfill_kline5m_shard{1..4}.log`

---

## ⚠️ 2026-09-11 16:40 更新：**回补失败 + baostock 拉黑服务器 IP（操作事故）**

### 事实
- 4-shard 全市场回补 15:44:28→15:49，**每 shard 目标 1248 只，fail=1219~1222**（每 shard 仅 ok≈18-20）。
- 现在服务器 `bs.login()` → **`10001011 黑名单用户`**。
- 覆盖核查：4991 只中 **仅 107 只**拿到 >40 天（max 133 天），其余仍 ~35 天。**目标"≥6 个月"未达成。**

### 根因（我方失误）
4 个 shard **并发登录 + 高频请求**（每只一次 query），baostock 侧限流/风控 → IP 拉黑。原脚本的 `--shard` 并发是错的用法。

### 教训 / 待办
1. baostock 只能**单进程、串行、低速率**（≤1-2 req/s）+ 退避重试；禁止多 shard 并发。
2. **同一 IP 短期内不要重试**（黑名单未解），先观察；或换出口/换源。
3. 5m 源现状（09-11 16:40）**三条全断**：
   - mootdx/TDX：宕（`build_kline5m` 当日 `完成: 0 只, 总行数 0`，5m 卡在 **09-09**）；
   - baostock：IP 黑名单；
   - akshare/东财：早先连接失败。
4. ⇒ **09-10 / 09-11 的 5m 缺失**，G1 2 周影子**无法开跑**（脚本已修好并部署，等在 `g1_shadow_daily.py`）。
5. 候选替代源（待验）：腾讯 `mkline`（需限速，防 WAF）、新浪 5m；或等 TDX 恢复（mootdx 可回溯 7 天，能自动补回 09-10/09-11）。

---

## ✅ 2026-09-11 17:00 处置完成：Sina 5m 兜底（短期缺口已补，影子已开跑）

### 补口结果
- 新脚本 `bt_research/fix_kline5m_sina.py`（**单进程 + 全局最小间隔 0.12s + 幂等 + 原子写**；新浪 5m `datalen=1023` ≈ 21 个交易日）。
- 对齐验证：`vol_ratio_med=1.0000`、`amt_reldiff_med≈0.4%`、`overlap 927 bars`（与现有 5m 同源同单位）。
- 全市场：**4991/4991，ok=4977 skip=14 empty=0 fail=0，新增 477,698 行（1127s）**；采样末日均到 **09-11**。
- ⇒ **09-10 / 09-11 的 5m 缺口已补**（每只 96 根 = 2 天）。

### 仍未解决
- **6 个月长历史仍缺**（Sina 只回溯 ~21 交易日；baostock 黑名单未解，且其历史同样只有 ~1 个月）。需另找长历史 5m 源。
- TDX 恢复后 mootdx 可自补近期；**Sina cron 建议保留作兜底**（TDX 是单源，已两次掉链）。

### 排程（已上线）
```
16:20 build_kline5m.py       (原有, TDX)
16:35 fix_kline5m_sina.py    (新增, Sina 兜底补口)
17:10 g1_shadow_daily.py     (新增, G1 只读影子)
```
**关键教训：任何依赖当日 5m 的任务必须排在 16:20 之后**（原影子设计写 15:30，那时当日 5m 尚不存在）。

### G1 影子首两日（⚠️ 仅 2 天、样本小，勿作结论）
| 日 | S0 全买 | G1 执行 | 否决数 | 走高误杀 |
|---|---|---|---|---|
| 2026-09-10 | −1.05% | **+0.87%** | 5 | 0 |
| 2026-09-11 | +1.25% | **+1.66%** | 2 | 1 |

两日 G1 均为正、且 09-10 规避有效；**但样本极小**，须等 2 周。产物 `output/g1_shadow/{D}.json`。
