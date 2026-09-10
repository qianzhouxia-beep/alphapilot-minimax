---
project: alphapilot
domain: data
title: westock（本地 CLI/MCP）K线源：可批量拉日线，但 volume 单位按板块不统一（688=股，其余=手）
date: 2026-09-11
status: observation
tags: [数据源, westock, K线, volume单位, 备用源, 缺口恢复]
---

# westock（本地 CLI/MCP）数据源档案

> 2026-09-11 补 09-10 K 线缺口时首次正式使用（WB-Win 本地执行）。定位：**K 线备用源候选**。

## 能力
- 本地 CLI/MCP，**支持批量日线 + 日期范围**（100 批 × 50 只，全市场 4991 只 ≈ 4 分 18 秒）；
- **不复权 day** 口径，可自算复权；
- 有 09-10 数据（TDX 中断当日可用）。

## ⚠️ 关键坑：volume 单位**按板块不统一**（确定性规则）
用 `amount/(volume×close)` 判单位：
| 板块 | 返回单位 | `amount/(vol×close)` | 转"股" |
|---|---|---|---|
| **科创板 `688xxx`** | **股** | **≈1** | **×1（勿再乘 100）** |
| 其余（主板/中小/创业） | **手** | **≈99.5** | **×100** |

- **交叉验证（Cursor 复核）**：`688001` westock = **19,050,931 股** vs 服务器库 09-09 真值 **19,050,900 股** → 同口径（股）。
- 首轮 4981 只里 **593 只比值异常，全部是 688**（比值恰 0.01 = 手误当股）。
- ⇒ **不能"一刀切 ×100"**，必须按 `symbol` 前缀判断（或按行 `ratio` 自适应）。

## 相关服务器事实（同口径）
- 服务器缓存 `kline_all.parquet` 的 **volume 口径 = 股**（历史多次审计）；`fix_kline_server.py` 也按 `ratio` 自适应 ×100 写入。
- ⇒ westock 的 688=股 与服务器库**一致**，不会造成口径冲突。

## 用途与限制
- ✅ 适合：**TDX 中断时的单日/多日缺口补齐**（配合"备份→追加→三重校验→原子写双路径"的合并脚本）。
- ⚠️ 不适合做**主源**：① 单位规则不统一（易踩坑）；② 本地 CLI/MCP 依赖本机（非服务器自愈）；③ 未做长期稳定性/延迟评估。
- 建议（待老板拍板）：`fix_kline_server.py` 多源 fallback 顺序 **TDX → 腾讯 → baostock**，westock 仅备选（因单位不统一）。

## 复用工具（WB-Win 侧，勿改）
- `_pull_kline_0910_westock.py`（拉取 + 单位换算 + 校验 CSV）
- `_merge_kline_0910_server.py`（服务器端合并：备份→追加→三重校验→原子写）

## 关联
- `knowledge/data_sources/2026-09-11-kline-0910-recovery.md`（事故与恢复全过程）
- `knowledge/data_sources/index.md`（K 线 volume 单位事实）
