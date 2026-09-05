# AlphaPilot 服务器端 Python 部署清单（Deploy Manifest）

> 用于跟踪服务器 `/home/ubuntu/alphapilot` 关键 .py 的部署基线（md5 + 最后修改时间）。
> 每次部署后更新本表；服务器与本地不一致 = 存在漂移，须人工核对方向。
> 关联：本地权威副本在 git 仓库；轨道 A/B 交易端策略走 `production_strategies/` 归档。

## 基线快照

| 文件 | md5 | 服务器最后修改 |
|---|---|---|
| `morning_live_fund_select.py` | `4bd86b611610c559f7621c941a08c783` | 2026-08-25 10:30（部署后，+ST 硬过滤） |
| `money_flow_gate.py` | `60f4e42f39fac5ddbc861a816932e2fb` | 2026-08-25 10:30（部署后，+ST 硬过滤） |
| `export_qmt_scores.py` | `d13896b4b47939e96bfd773f0a42876f` | 2026-08-26 18:56（部署后，candidates.json +fund_hard_fail） |
| `api_server.py` | `613e83270c39f8612660ea9376bef1a9` | 2026-08-24 23:00:41.973079403 |
| `live_momentum_scanner.py` | `d0d82dd81239b474eda0119996686be3` | 2026-08-25 10:30（部署后，+ST 硬过滤） |
| `alphapilot_pipeline_v3.py` | `1c866a159feb239803ab67eb8175e09a` | 2026-08-25 10:30（部署后，+ST 硬过滤） |
| `recommend.py` | `00d5ed17522724f79221dc10ea02ba45` | 2026-08-19 07:40:32.437745695 |
| `vm25_scorer.py` | `8f8b69113a848c5c8c07fd28bd5d65a2` | 2026-08-04 14:05:36.494149354 |
| `features_v2.py` | `67f6b0ff6487194932bc57e980ad174e` | 2026-08-03 00:00:59.440547557 |
| `auto_factor_engine.py` | `cbd63d3f4759f5726ad009cebcd20aa4` | 2026-07-12 12:10:29.860968371 |
| `trade_executor.py` | `1438786117641fc9e07a3c5e700b7b0d` | 2026-08-09 19:11:55.146984585 |
| `run_server.py` | `8631e6658b696957328a60bce64141a8` | 2026-08-18 23:25:45.719211413 |
| `paper_trading_signals.py` | `4939520bb772df7ebb9894f43c7b3f8a` | 2026-08-24 23:00:42.561099770 |
| `scripts/build_score_top10.py` | `dd3f7c6456cffe64c5dc9e1464bc9420` | 2026-08-06 10:12:44.569502911 |
| `scripts/archive_daily_picks.py` | `d0f0ffcc692bc5cfffac0ced55466757` | 2026-07-26 17:44:06.081179887 |
| `scripts/accumulate_top2_t1t5.py` | `a57c5a0c22c3281d78462421599e888c` | 2026-08-15 22:38:13.304230085 |
| `scripts/pipeline_healthcheck.py` | `94b0893ccaea73d7b5d0644bb9cc3fbe` | 2026-07-19 08:36:05.091735338 |
| `fix_kline_server.py` | `6f453920597ea7f248ab877d3d4f169e` | 2026-08-24 23:40:xx（部署后） |
| `scripts/data_readiness_gate.py` | `396094c74754464fbfd6e77956411747` | 2026-08-25 00:12（部署后） |
| `scripts/chip_missing_alert.py` | `e807a9a0c8e5bff09c35040760f0ff9e` | 2026-08-25 00:12（部署后） |
| `scripts/check_chip_batches.py` | `082ab72372654455fe4f6b8ca56186dc` | 2026-08-25 00:30（部署后） |

## 数据脚本（08-24 起纳入治理）

> 08-24 事故后纳入部署基线。本地权威副本一律在 `production_strategies/server/`。

| 文件 | md5（服务器） | 说明 |
|---|---|---|
| `data_freshness_check.py` | `eca910cfba32b7d8797a52cd43637753` | 盘后/盘中新鲜度（v2 查 K 线实际日期 gap） |
| `daily_coverage_check.py` | 服务器根目录（见 `production_strategies/server/daily_coverage_check.py`） | 全数据时间+覆盖率双维检查；cron 已从 16:25 挪到 **18:15**（WorkBuddy 筹码上传后） |
| `freshness_coverage_check.py` | 服务器根目录（见 `production_strategies/server/freshness_coverage_check.py`） | K 线覆盖率 <90% 告警（16:20） |
| `scripts/pull_chip_from_kline.py` | `e4ad87f0cad44dd238b405586aee2388` | K 线推演筹码（**非生产口径**，生产 chip 走 WorkBuddy 上传） |
| `scripts/sector_fingerprint_report.py` | `cb0da5bd559b18ed12e72ee6a600b83c` | 资金指纹板块方向日更（05:30 cron；晨报推送 + 软加分输入） |

## 部署记录

| 日期 | 文件 | 动作 | 备注 |
|---|---|---|---|
| 2026-08-24 | money_flow_gate.py | 覆盖（修复 404） | 08-04 旧版备份 .bak_20260804/.bak.20260824；本地新签名含 min_change_pct/require_above_vwap |
| 2026-08-24 | live_momentum_scanner.py | 覆盖（合并版） | 含本地 CapitalPulse+垃圾值防御+服务器质量门控+fallback 近涨停过滤；旧版 .bak_20260824_merge |
| 2026-08-24 | api_server.py | 覆盖 | 用 min_change_pct/require_above_vwap 新参数调用资金门；旧版 .bak_20260824_merge；已重启 alphapilot-api |
| 2026-08-24 | paper_trading_signals.py | 覆盖 | 用新参数调用资金门；旧版 .bak_20260824_merge |
| 2026-08-24 | morning_live_fund_select.py | 覆盖（+签名自检） | 缺 min_change_pct/require_above_vwap 即 SystemExit；旧版 .bak_20260824_guard |
| 2026-08-24 | api_server.py | 覆盖（+签名自检日志） | 静默降级时打日志；旧版 .bak_20260824_guard；已重启 alphapilot-api |
| 2026-08-24 | paper_trading_signals.py | 覆盖（+签名自检日志） | 静默降级时打日志；旧版 .bak_20260824_guard |
| 2026-08-24 | fix_kline_server.py | 覆盖（WORKERS 16→1） | 16 并发触通达信限流→K 线 08-24 仅 960 只→筹码 1192 只停 08-21；串行后 4991/4991 补齐，chip 重建 4991 只全 08-24；旧版 .bak_20260824_workers16 |
| 2026-08-24 | fix_kline_server.py | 覆盖（+覆盖率门槛） | 根治C：最新日覆盖率 <90% 拒绝写入残缺 K 线，防「并发限流后仍落盘」；旧版 .bak_20260824_workers16 |
| 2026-08-25 | scripts/data_readiness_gate.py | 覆盖（chip 覆盖率检查） | 根治B：chip 检查从「众数日对照」改为「最新日覆盖率 ≥95%」，拦截半截数据（3800/4992=76%）；旧版 .bak_20260824 |
| 2026-08-25 | scripts/chip_missing_alert.py | 新增 | 根治B：chip 覆盖不足时写 data_alerts.json 告警，不覆盖真实筹码（替代误用的 pull_chip_from_kline 修复） |
| 2026-08-25 | scripts/check_chip_batches.py | 新增 | 根治D：上传前批次完整性校验（缺批次/覆盖不足/日期不符 → 禁止上传） |
| 2026-08-25 | cron | 调整 | daily_coverage_check 16:25 → 18:15（WorkBuddy 筹码上传后复查） |
| 2026-08-25 | scripts/sector_fingerprint_report.py | 新增部署 | 资金指纹板块方向日更；05:30 cron（SFTP 写临时文件安全安装）；已跑通并推送企业微信成功（ok=True） |
| 2026-08-25 | morning_live_fund_select.py | 覆盖（+资金指纹软加分） | 动量失效日启用：指纹 H+5 前6行业 score×1.05，其余×0.98，不硬剔；旧版 .bak_20260825_fingerprint；部署后 import+单测通过 |
| 2026-08-25 | money_flow_gate.py | 覆盖（+ST 硬过滤） | 08-25 事故：*ST威领(002667)被 Track B 买入。apply_money_flow_gate 开头新增 _is_st 硬剔除（ST/*ST/S*ST/退市），命中即移除并打日志；旧版 .bak_20260825_st |
| 2026-08-25 | morning_live_fund_select.py | 覆盖（+ST 硬过滤） | pool 加载后剔除 ST/*ST/退市（防 tail 回填与资金门漏网）；旧版 .bak_20260825_st |
| 2026-08-25 | export_qmt_scores.py | 覆盖（+ST 硬过滤） | export_fullpool_live 与 main 导出均剔除 ST（保底，即使 daily_recommend 残留旧数据）；旧版 .bak_20260825_st |
| 2026-08-26 | export_qmt_scores.py | 覆盖（candidates +fund_hard_fail） | Top10 `candidates.json` 增加 fund_hard_fail/main_net_5d/main_net_3d/fund_pos_days_5；旧版 .bak.20260826_fund；已补跑今日导出 |
| 2026-08-25 | live_momentum_scanner.py | 覆盖（+ST 硬过滤） | 主路径与 fallback 写入 daily_recommend.json 前剔除 ST（源头上不产出风险股）；旧版 .bak_20260825_st |
| 2026-08-25 | alphapilot_pipeline_v3.py | 覆盖（+ST 硬过滤） | 05:00 管线写回 recommendations 前剔除 ST（最上游兜底）；旧版 .bak_20260825_st |
