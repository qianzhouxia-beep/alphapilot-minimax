---
project: alphapilot
domain: architecture
title: 数据可靠性分层方案 — 消除"经常出这种 bug"的结构缺口
date: 2026-09-09
status: decision
tags: [data, architecture, readiness, spof, chip, data-contract]
---

# 数据可靠性分层方案（老板问：数据常出错，架构要不要调）

## 触发
09-09 连续踩数据坑（fullpool_live f84/f170 乱值、hithink 429、PC 关机致 chip 未传），老板问"有没有干净方案、架构要不要调整"。

## 实测现状（决定"明天 5 点会不会挂"）
- **服务器 crontab 显示 05:00 链路上游已几乎全在服务器**：K线(mootdx/东财)、资金流 21:00、extra_factors 21:20、重训 21:30、margin/LHB 04:40-45、04:50 data_readiness_gate（预警+自动修复，默认不阻断）、16:45 收盘资金流已"替代本地 WorkBuddy automation"。
- **唯一残留 PC/WB 依赖 = 筹码 chip**：`refresh_all_data.py` 注释明写"筹码数据由本地 WorkBuddy 通过 upload-chip-data API 上传"。服务器无自采源。
- 09-09 实测：chip_data_all.json 停在 **09-08 16:13**（PC 未开机）→ **09-10 05:00 管线将用旧一日 chip**（v25 106 维中 6 维），其余 14 项 readiness 全绿（K线 09-09 16:16 / 资金流 21:00 / extra_factors 21:31）。
- 结论：明天不会崩，是"1 个特征组降级 + readiness 报 warn"；若 chip 源长期无二路，重复发生会积累。

## 根因：三个结构缺口
- **G1 无数据契约**：字段在写入端无 schema/范围校验，垃圾一直流到消费端才被补丁拦（f84/f170 到 export 才兜底）。
- **G2 健康检查碎片化**：服务器 ≥8 个监控并存（data_readiness / data_health_check / freshness_coverage_check / daily_coverage_check / data_accumulation_check / shadow_daily_health / check_sector_flow_health / preflight_checkpoint…），无单一"今日数据完备且 sane"布尔供决策点统一消费。
- **G3 个人机 SPOF**：凡"只产自 PC"的数据（chip）天然脆弱；QMT/TDX 执行受 PC 制约是另一类（本机可控）。

## 方案（分层，L1→L6）
- **L1 数据契约层**：共享 `data_quality.py`（字段∈范围/类型/交叉一致/覆盖率），在每个**写入端**生效（本次 f84/f170 修复即模板），垃圾死在门口 + 落 `data_alert.json`。
- **L2 统一就绪闸**：8+ 监控收敛为一个 readiness 视图，按决策时刻出 `{stage}_ready.json`（05:00 / 09:35 / 16:15），策略逐项 block/warn/fallback-to-yesterday(标 stale)。
- **L3 源冗余+覆盖 SLA**：关键产物≥2 源（K线已 3 源；资金流 tdxhub+东财；chip 仅 1 源→补服务器自采或二路）。
- **L4 消除 PC SPOF**：迁移每个 05:00/09:35 相关拉取到服务器——**下一目标 chip**（与 16:45 server_close_fundflow 同模式）。
- **L5 数据版本化**：daily 快照（fullpool_live 已开始留、sector_flow 历史待补），坏日可回补、事件研究有序列。
- **L6 单页告警**：每早一条 WeCom 就绪判语（全绿/N 项降级/阻断），人 10 秒看完。

## 模型架构：不需要重构模型，要调的是"数据进模型"的边界
选股模型（V25）数学本身不背锅；建议把**数据质量/来源当一流向量**：每股票日记录 (chip 是否陈旧 / 资金流是否 fallback / kline 覆盖率)，①关键组坏则门 05:00，②候选评分标注降级，③随预测归档——事后能归因"这笔是陈旧数据选出来的"。这是唯一值得动的架构层（不改打分权重、不重训）。

## 待办
1. chip 迁移服务器（L4 落地，最优先；09-10 先用旧一日 chip 顶着）。
2. 统一 readiness 收敛（L2）。
3. chip/资金流 二路源（L3）。

## L4 实测定调（22:55 补充）+ 修正（23:15）
- **服务器直连东财 datacenter stock_cyq_em = 被断**（RemoteDisconnected 实证）→ chip 真实源自采"上云"路线被网络堵死。
- **Mac 同源 stock_cyq_em 可达**（但今晚也被临时风控，抖动）。
- **L4 修正（用户反问点破：单点挪窝≠去单点）**：
  - ❌ 原表述"把生产者从 Windows PC 挪到 Mac"是错的——Mac 当唯一生产者 = SPOF 平移。
  - ✅ 正确目标 = **≥2 路生产者并存 + 上传去重**（HA）：Windows WB + Mac 各配每日任务，谁传成功算谁的；任一台坏不影响。服务器端只需上传接口支持"来源/日期标记 + 同日多传去重"，改动极小。
  - 终极治本（待验证、不保证）：服务器直连真实源（当前被云 IP 风控；可试降频/换 host/官方渠道/同花顺系），彻底去掉个人机角色。
  - 兜底纪律（已部分就位）：任一路断更 → readiness warn + 标 stale，模型/闸门知情，决策不受脏数据污染；断更 1 天真实代价 = 6/106 维旧一日，是降级噪声不是灾难。
- **23:25 双服务器互拉实测（用户提议"用一台服务器拉另一台"）**：
  - 新加坡 43.156.119.47：python3.12 + **akshare 1.18.64 已装**（与上海同版）；push2his **23:20 裸 curl 通**（返回正常 klines）→ 服务器间互拉"网络层可行"。
  - 但 akshare stock_cyq_em 在新加坡立即 RemoteDisconnected；**23:29 再 curl 3 档参数全返回东财安全验证页（STime/SNum HTML）** → 新加坡也在几分钟内被风控。
  - **结论：东财对数据中心/云 IP 风控是全方位的**（上海断、新加坡短窗通后被封、Mac 家宽也抖）——"换台服务器当生产者"不能根治，只是多一路临时可用出口。服务器间互拉的定位 = 多一路兜底探测，不是 chip 日常主生产。
  - chip 日常最优结构（更新）：多路家宽(PC/Mac 双活,住宅 IP 相对宽容)为主 + 上海/新加坡做校验+告警；若某云 IP 长期不被风控（需观察恢复曲线）再议切主。
- `scripts/pull_chip_from_kline.py`（K线推演口径）服务器 07-20 已有，但 `data_readiness_gate.py` L340-342 注释明确**否决**其作自动修复（会污染真实筹码口径），仅 `chip_missing_alert.py` 告警。
- 映射细节待一次校验：生产文件 chipProfitRate=92.45(百分数)/conc90=7.07 vs akshare 获利比例=0.958(小数)/90集中度=0.0594 → 需定 adjust/字段换算/closePrice+name 补齐，对照最近一次已知良品（09-08 上传档）。
- 今晚过夜回补 = 一次性救急补 09-09，非日常生产者；定位见 checkpoints 23:10 行。

## 证据
服务器 crontab；`refresh_all_data.py` 头注释；09-09 data_readiness.json 全绿 + chip 09-08；本卡同源结论已回帖 Issue #6。
