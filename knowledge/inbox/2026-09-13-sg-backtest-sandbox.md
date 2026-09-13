---
project: AlphaPilot
domain: architecture
title: 重算力外移新加坡沙箱（上海 OOM 根治）
date: 2026-09-13
status: decision
tags: [compute-host, sandbox, oom, backtest, singapore, walkforward]
---

# 重算力外移新加坡沙箱（上海 OOM 根治）

## 结论

**全市场回测/训练/因子挖掘一律在新加坡服务器（`43.156.119.47`）跑，不再在上海生产机（`150.158.100.236`，3.6 GB）跑。**

触发：`rd_workshop/walkforward_oos.py` 全量在上海**连续两次被 OOM killer 杀掉**（`anon-rss 3.14 GB`），第二次发生在建面板阶段（即使已做过两轮内存优化）。

## 关键事实

- 新加坡：**15.6 GB 内存 / 12.4 GB 可用 / 4 核 / 178 G 磁盘 / load 0.08**（是上海的 4.3 倍内存）。
- 新加坡**本没有 A 股生产数据**（无 `kline_all.parquet`、无 `models/`）→ 已建沙箱 `/home/ubuntu/bt_sandbox/`，数据从上海**单向下拉**（kline 56 M + 资金流 63 M + 侧车 ~5 M + 模型 1.5 M ≈ 126 MB）。
- **版本陷阱**：SG 系统默认 pandas **3.0.3** / xgboost 3.3.0，生产是 pandas 2.3.3 / xgboost 3.2.0 → 必须用 `pip --target` 装生产同版本（`python3-venv` 在 SG 不可用）。否则结果不可比。
- 数据通道：SG→上海 免密 `-i /home/ubuntu/.ssh/alphapilot.pem ubuntu@150.158.100.236`（SG crontab 原本就在用）。

## 验证（决定性）

300 只 × 2 折 smoke，**SG 与上海 AUC/IC 16 位小数完全一致**（折1 cand AUC 0.6827003460611245，折2 ΔAUC −0.00808）⇒ 沙箱是**同口径算力外移**，不是另一套算法。RSS 1.08 GB / 15.6 GB。

## 操作

`python3 scripts/sg_sandbox.py --sync --run "<脚本>"`（`--sync-data` / `--status` / `--fetch`）。
运行前缀：`ALPHAPILOT_ROOT=/home/ubuntu/bt_sandbox/alphapilot PYTHONPATH=/home/ubuntu/bt_sandbox/pylibs nice -n 10 python3 -u ...`

## 边界

- SG 还跑 crypto 纸盘 / HK 纸盘 → 重活必须 `nice -n 10`；负载升高时需重新评估（可 `taskset` 限核）。
- 结论/口径仍以上海生产为准；沙箱只是算力。
- **勿混**：港美股数据归属 SG（2026-09-10）与本条（A 股重算力外移）是两回事。

## 链接

`.cursor/rules/compute-host.mdc` · `MEMORY.md` · `knowledge/decisions/2026-09-13-compute-host-split.md` · `scripts/sg_sandbox.py`
