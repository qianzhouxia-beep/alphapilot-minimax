---
project: alphapilot
domain: data
title: overnight_signal 前滚缺陷定案与修复（ingest v1.1）——缺行优于错值
date: 2026-09-16
status: conclusion
tags: [us-overnight, ingest, g1, data-integrity, sina-lag, forward-roll]
---

# 结论：cn 09-16 拿到 us 09-14 陈旧值 = 上游发布延迟 × 前滚逻辑静默复用

## 现象
`data/us_daily/overnight_signal.json` 尾部：
```
cn=2026-09-15 ← us=2026-09-14  ✓ (NVDA −3.36% / QQQ −0.80%)
cn=2026-09-16 ← us=2026-09-14  ✗ 与上条一字不差（应为 us=09-15）
```

## 根因（两层，务必分开）
1. **上游发布延迟，_不是_ ingest 失败**：09-16 05:30 日志 `all ok`，但新浪美股日线当时
   最新只到 09-14。美市 09-15 收盘 = 北京 09-16 04:00，05:30（+1.5h）该 bar 尚未发布；
   当晚 23:51（+19h）已可见。**同一进程重跑即拉到 09-15**。
2. **前滚逻辑静默复用（真缺陷）**：`prev_us_session` 回扫 ≤5 天取"最近可得"，预期 09-15
   缺失时静默复用 09-14 ⇒ 新 cn 日期携带陈旧外盘值、无任何标注。

### 真实值对照（2026-09-16 23:51 实拉新浪核实）
| us 交易日 | NVDA | QQQ |
|---|---|---|
| 09-14（被误用的） | −3.36% | −0.80% |
| **09-15（应被用的）** | **+0.5736%** | **−0.6543%** |

符号相反：正确的 `cn=09-16` `g1_flag=none`，被污染的账本写成 `ai_rebound_watch`。

## 修复（`scripts/ingest_us_daily.py` v1.1，已部署）
- 新增美股日历 `US_MARKET_HOLIDAYS`(2025–2027) + `expected_us_session(cn)`：唯一允许的
  美市日 = 严格早于 cn 的最近**交易日**；周末/假日自动跳过（保留日历补齐语义）。
- 预期美市日缺失 ⇒ 显式 `us_date=<预期>, nvda_ret=null, qqq_ret=null, g1_flag="stale"`，
  **绝不前滚**。周末跨日（cn 周六/日 ← us 周五）仍正常映射，不受影响。
- 05:30 若预期缺失，日志 `WARN … -> row marked stale (no forward-roll)`。
- `<out_dir>/backfill_notes.json`：人工订正行持久标注 `backfilled=true` + `backfill_note`
  （跨次重生成保留）。单测 `bt_research/_ut_us_overnight_signal.py` **15/15**。

## 回填与订正（已完成）
- `cn=2026-09-16` → `us=2026-09-15`，NVDA +0.5736% / QQQ −0.6543%，`g1_flag` 订正为 `none`，
  带 `backfilled=true`。
- 同日 `output/research_gates/g1_20260916.json`（flag=us_date/rets 已订正）与
  `output/qmt_scores/20260916.candidates.json` 的 `g1_*` 标注已同步重算（仅标注，无重排）。

## 调度加固
- 05:30 主跑之外新增 **07:00 / 09:20 兜底重跑**（`run_us_ingest_daily.sh`，幂等；09:20 在
  09:38 G1 stamp 前）。遵循本仓"主跑 + 兜底"惯例（如资金流 16:45/21:30）。
- `run_us_ingest_daily.sh` 改为 ingest 非零退出也照常 stamp+mirror，末尾透传 rc
  （上游部分失败时镜像不再冻结）。

## 红线 / 未决
- **本轮刻意不新增数据源、不改 G1 阈值**（无 TDX↔新浪同日对照，不拍数）。
- 若新浪日线在次日 09:20 前仍不发布，`cn` 行会是**显式 stale（空值）**——"缺行优于错值"，
  明早 05:30/07:00/09:20 三跑后即可判新浪发布时刻；若仍晚，再议"实时报价补充源"（需老板拍板）。
- G1 仍 **shadow_annotate_only**，rebound_bonus 未进分：本次账本脏，**生产分未污染**。

## 部署件 md5（服务器 /home/ubuntu/alphapilot）
- `scripts/ingest_us_daily.py` `86563fdcdde1ae6456e0a2df938d26a9`
- `scripts/run_us_ingest_daily.sh` `6cec7d894072662a7d88ec68eadcb155`
- `data/us_daily/backfill_notes.json` `8fdf5eec8d90b7ab213edc1a3804bc92`

## 关联
- WB 工单：Issue#6 评论 `5699933328`
- `knowledge/ops/gate_spec_G1G2_20260915.md` §7
- `knowledge/ops/checkpoints.md` 2026-09-16 23:55 行
