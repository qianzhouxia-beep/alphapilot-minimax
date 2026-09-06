---
project: alphapilot
domain: data
title: 全量影子/观察链路体检 2026-09-06：无新空转，修复 rd_health 静默告警缺陷
date: 2026-09-06
status: conclusion
tags: [影子, 体检, 空转, rd_health, wecom, 静默失败, 待验证]
---

# 全量影子/观察链路体检（2026-09-06）

触发：资金三角影子发现 9 天空转后，用户要求把"之前部署的影子/观察"全部复查一遍，杜绝再次空转。

## 方法

一次性服务器审计探针 `bt_research/_cmp/_audit_shadows_20260906.py`：
- 09:35 morning 链 9 个 shadow 模块文件存在性 + 各自输出 jsonl 的行数/首末 asof/mtime
- rd_workshop 两个每日双跑（换手/weakscore）shadow_log.csv 全量
- 盘后 monitor 输出（reversal / shadow_top2 / market_tone / top2_t1t5 / retrain_status）
- 各相关 cron 日志 mtime + 末行（判定最近交易日 09-04 是否都跑）
- crontab 全量对照，无遗漏条目

## 体检结论

### 正常链路（无空转，数据按预期积累）
| 链路 | 状态 |
|---|---|
| 09:35 四影（market_flow_condition / wind_regime / weak_score / live_tone） | 09-03/09-04 各 append 2 行，mtime=最近交易日 |
| shadow_top2 主影子（SHADOW_MODEL_DIR） | 15 交易日历史（08-17→09-04），09-04 有 append |
| shadow_top2_report 16:26 | 生成 + 企微 markdown + Excel 推送 **ok=True** |
| 换手双跑 22:20 | shadow_log.csv 5 连正 diff（09-04 完成，仅 09-02 超时缺 1 天已修复） |
| weakscore 双跑 00:20(2-6) | 3 连正 diff（09-02/03/04，09-05 周六 01:31 完成），全连续无超时 |
| reversal shadow 14:50/16:30 | 9 天历史，09-04 正常 |
| top2_t1t5 16:25 / market_tone 09:33 / wind_investor_flow 21:15 / intel_brief 08:50 / send_daily_picks_excel 06:20 | 全部 09-04 正常，wecom 推送 ok=True |
| daily_retrain 21:30 | 每日跑；AUC 安全门连续拒绝 = **设计内保护**（08-21 起模型冻结） |

### 修复的静默缺陷（唯一发现）
**rd_workshop/rd_health_check.py**（每天 2 次被 cron_rd_monitor + shadow_top2_report 尾部 subprocess 调用）：
1. 企微告警 `from wecom_push import send_markdown` 失败——模块在 `scripts/` 下，代码只 `sys.path.insert(0, ROOT)` → **每个真实告警都从没发出去**（wecom skip 天天打日志）。
2. 把 `auc_gate_rejected`（安全门正常保护拒绝）误判为"最近重训失败"告警 → 每天 2 次误报，rc=2，噪音会淹没真实告警。

修复（本地 + scp 服务器，实测 RC=0、RD HEALTH OK）：
- auc_gate_rejected → 归入 notes（正常保护），仅非安全门错误才 alert
- wecom import 双路径（先 scripts 后 ROOT）

### 09-07（周一）待首验证 5 项
1. fund_bonus_shadow → `fund-bonus shadow appended` + jsonl 创建（模块 09-06 补传）
2. market_regime_shadow / 3. sector_quality_shadow → 同上
4. vp_factor_shadow → `vp-factor shadow appended`（模块在，morning 尾段已确认调 write_shadow，9/4 上传当天 09:35 已过所以 jsonl 未建属预期）
5. C 组新 cron：breakout_monitor 16:28 / top2_excess 16:29 首跑建 log（今天 top2_t1t5_excess.json 09-06 12:13 = 部署时手动测试产物，非异常）

## 局限
- QMT/TDX sim 端影子（SHADOW-B1 5min / SHADOW-CALL / SHADOW-G1 等）在用户本地交易端运行，服务器审计无法覆盖，需在交易端侧确认部署后已重启加载。
- 审计基准 = 最近交易日 09-04（周五），周末各工作日 cron 无新记录属正常。

## 下次看
- 09-07 09:36 后：`grep "shadow appended" output/logs/l2_refresh.log` 应 ≥8 条/天
- 09-07 16:30 后：`ls output/logs/breakout_monitor.log output/logs/top2_excess.log`
- checkpoint 顶行已记
