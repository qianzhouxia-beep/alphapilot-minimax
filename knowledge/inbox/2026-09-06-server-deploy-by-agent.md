---
project: alphapilot
domain: architecture
title: 服务器操作分工约定：Agent 直接执行上传/变更（防漏传空转）
date: 2026-09-06
status: decision
tags: [分工, 服务器, 部署, 空转, 防漏]
---

# 服务器操作分工约定（2026-09-06 用户拍板）

## 决策

**需要上传服务器 / 在服务器上做变动的，Agent 直接执行，不再询问、不交给用户。**

## 背景

- 上海 ECS `/home/ubuntu/alphapilot` 的一切上传/变更历来由 Agent 完成，用户从未参与。
- 若让用户手动操作，容易漏传。资金三角影子 9 天空转的根因之一：`fund_bonus_shadow.py` 等模块
  在本地存在但从未上传服务器 → `morning_live_fund_select.py` 每天静默 skip。
- 用户原话（2026-09-06 16:38）："以后记住了，因为之前服务器的上传等操作都是你在做，我从来没有参与过。
  为了避免以后漏掉上传服务器或在服务器上做变动，需要上传的时候，你就直接上传就可以了。如果让我来，可能就会漏掉。"

## 边界（例外仍由用户手动）

- **交易端文件**（QMT python 目录 / TDX `PYPlugins\user`）仍由用户手动复制/导入——
  规则见 `.cursor/rules/production-strategies.mdc` 第 5 条「部署由用户手动执行（2026-08-29 固化）」。
  例：09-06 模拟端 4 份（A QMT v2.40 / A TDX v2.31 / B QMT v2.12 / B TDX v1.20）等用户自行上。

## 执行纪律

1. 服务器变更后照常自验：`py_compile` / 本地-远端 md5 比对 / 关键字段计数（用 python 探针，勿用
   PowerShell+ssh 里的 grep `\|` —— 引号会被吞导致假阴性）。
2. 变更留痕：CHANGELOG（若涉生产文件）+ checkpoints.md + 必要时 inbox 卡。
3. 需用户注意的（如"需手动复制到交易端"）在回复里明确列出。

## 本次一并完成

- 服务器端竞价影子 2 文件部署并核验：`pre_market_gate.py` + `export_qmt_scores.py`
  （备份为 `*.bak_0906`；md5 与 `production_strategies/server/` 归档一致；
  export 含 pre_market_gap_pct/call_amount_wan/call_volume_hand 各 5 处、gate 含 pre_market_archive 2 处）。
- 09-07 起：09:25:55 cron 落 `output/pre_market_archive/{date}.json`，09:36 导出带 pre_market_* 影子字段
  → 模拟端 `[SHADOW-CALL]` 才有数据可读（否则模拟端会静默跳过）。

## 相关
- MEMORY.md 顶部「服务器操作分工约定」节
- checkpoints.md 2026-09-06 18:40 行
- CHANGELOG.md 2026-09-05 竞价量影子段
