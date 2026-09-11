---
project: alphapilot
domain: data
title: TDX 盘后行情中断定性=服务端异常（非服务器 IP 封禁）；腾讯不复权日K 验通为备用源，但 qfq 滞后一天
date: 2026-09-10
status: conclusion
tags: [kline, tdx, mootdx, pytdx, 备用源, 腾讯, gtimg, 数据源, 复权, 二级诊断]
---

# TDX 行情源中断定性 + 腾讯备用源（2026-09-10）

## 结论（2-3 句）

2026-09-10 盘后 K 线抓取全失败（服务器 `0/4991`）。**跨网络二分诊断定案：不是服务器出口 IP 被封，是 TDX 服务端异常**——
广东广电（`119.2.202.7`）独立网络路径完整复现同一故障（静态元数据通道通、行情数据通道死），
**故正确处理=等自愈，不必折腾 HA/换节点**。
副产品：**腾讯不复权日K 是可用应急通道**（3 只已验通），但**前复权 `qfq` 会滞后一天**，必须用不复权再自算复权。

## 证据

### 故障特征（服务器 + WB 双网络路径一致）
| 层级 | 结果 |
|---|---|
| TCP / 握手 | ✅ 可达（服务器 14/38 HQ_HOSTS 开；WB 6 节点 5 可达） |
| 静态元数据 | ✅ `get_security_count(0)` = 24238 |
| `get_security_bars` | ❌ **全部空返回**（日K/5min/1min、个股/指数、沪深全试） |
| `get_security_quotes` | ❌ 空返回 |
| `get_minute_time_data` | ⚠️ 返 240 根但**内容乱码**（平安银行末价 4547.68，不可能） |
| 库版本 | pytdx 1.72 与 **tdxpy 0.2.7（与服务器同库）** 症状一致 |
| 服务器侧报错 | `get_security_bars` → `TdxFunctionCallError: 'calling function error'` |

**判别逻辑**：故障在一条**非机房的独立网络路径**上完整复现 → 排除"服务器出口 IP 被挡"；
特征"静态元数据通 / 行情通道死"→ **TDX 服务端侧异常，全客户端受影响**。

### 影响与自愈
- `data/kline_cache/kline_all.parquet` 与根副本 max 停在 `2026-09-09`（09-10 行=0）。
- `fix_kline_server.py` 取**近 20 日窗口**、按 `symbol+date` 去重 → **下次成功抓取会自动补上 09-10**（K 线自愈）。
- 但**影子 marker 不自愈**：`shadow_p1_down_daily.py` 默认 `last_archive_day()` 会跳过 09-10，
  须在 K 线到位后显式 `--asof 2026-09-10` 补录（因归档永久保留 + K 线 20 日窗口，**20 日内补即可**）。
- 同源波及所有 mootdx 盘后 job（`build_kline5m.py` 当日亦 0 行，恢复后需重跑）。

### 备用源：腾讯 gtimg（WB 本机验通）
| 股票 | 09-10 日线（腾讯不复权，vol=手，未 ×100） |
|---|---|
| 000001 平安银行 | O 11.68 / H 11.86 / L 11.66 / **C 11.85** / vol 867,632 |
| 002636 金安国纪 | O 68.49 / H 76.45 / L 68.31 / **C 76.45**（+9.9%）/ vol 649,689 |
| 600519 贵州茅台 | C 1285.13 |

**⚠️ 两个必须知道的坑**：
1. **腾讯前复权 `qfqday` 滞后一天**：600519 的 qfq 末根仍是 09-09，改用**不复权 `day`** 才拿到 09-10。
   若走腾讯补录，**必须用不复权 + 自算复权**，否则会静默丢一天。
2. 东财 `push2his` 从 WB 本机亦被拒（`Remote end closed`）→ 与服务器同因，**不该指望东财这条**。

## 影响 / 下一步

- 本次正确处置 = **等 TDX 自愈**（20 日窗口兜底）；不需 HA、不需换节点、不需改代码。
- 若确需提前补 09-10：腾讯不复权是唯一验通路径；但**混源风险**（腾讯口径 vs 缓存 TDX 口径的复权连续性）
  须先过"K 线单位铁律 `amount/(volume×close)`"校验再写入——**建议仅在确有分析需求时才做**。
- 方法论价值：这是"**跨网络二分诊断 + 双库交叉验证**"的标准案例（WB 已固化为技能 `tdx-kline-source-probe`），
  下次"取不到 K 线"可直接复用判据链。

## 关联

- 触发事故：`knowledge/ops/checkpoints.md` 2026-09-10 17:24 / 17:50 行
- Issue#6 WB 探测回帖：comment 5616788946；探测产物 `bt_research/_wb_kline_0910/probe.json`（WB 侧）
- 相关铁律：`MEMORY.md` K 线单位铁律（缓存=股 / 通达信=手；`amount/(volume×close)` 判定）
- 相关脚本：`fix_kline_server.py`、`build_kline5m.py`、`rd_workshop/shadow_p1_down_daily.py`
