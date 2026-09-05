# 服务器数据脚本归档（Data Governance Archive）

> 2026-08-24 事故后新增。**所有服务器数据脚本的本地权威副本在此目录**，
> 与 `DEPLOY_MANIFEST.md` 配套追踪部署基线。

## 目录文件

| 文件 | 角色 | cron | 部署目标 |
|------|------|------|----------|
| `fix_kline_server.py` | K 线补全（mootdx 串行 + **覆盖率门槛**） | 16:15 | 服务器根目录 |
| `data_freshness_check.py` | 盘后/盘中新鲜度（v2 查实际日期） | 15:40 | 服务器 `scripts/` |
| `freshness_coverage_check.py` | K 线覆盖率 <90% 告警 | 16:20 | 服务器根目录 |
| `daily_coverage_check.py` | 全数据时间+覆盖率双维检查 | **18:15**（原 16:25） | 服务器根目录 |
| `data_readiness_gate.py` | 04:50 数据就绪闸门（**chip 覆盖率 ≥95%**） | 04:50 | 服务器 `scripts/` |
| `chip_missing_alert.py` | chip 覆盖不足→写 data_alerts 告警（不覆盖真实筹码） | 由 readiness 修复链调用 | 服务器 `scripts/` |
| `check_chip_batches.py` | **上传前**批次完整性校验（缺批次/覆盖不足/日期不符→禁止上传） | 手动（WorkBuddy 上传前） | 服务器 `scripts/` |
| `pull_chip_from_kline.py` | K 线推演筹码（**非生产口径**） | 手动 | 服务器 `scripts/` |
| `sector_fingerprint_report.py` | 资金指纹板块方向日更（晨报推送 + 软加分输入） | 05:30 | 服务器 `scripts/` |

## 关键链路（2026-08-24 复盘后）

```
16:15 fix_kline_server（mootdx 串行 + 覆盖率门槛 <90% 拒写）
  → 16:18 sync_kline_root
  → 16:20 freshness_coverage_check（K线覆盖率告警）
  → 18:15 daily_coverage_check（全数据复查，含 chip 覆盖率）
  → 04:50 data_readiness_gate（chip 最新日覆盖率 ≥95% 才 ready）
```

## 服务器 cron 修改铁律（08-25 事故教训）

**绝对禁止** `echo '<b64>' | base64 -d | crontab -` 管道写入——非交互 SSH 的
stdin 会提前 EOF，**静默清空整个 crontab**（08-25 实测踩坑：crontab 从 129 行
变 0 行）。正确做法：

1. 先用 SFTP 把新 crontab 写到 `/tmp/crontab_new.txt`
2. 再 `crontab < /tmp/crontab_new.txt`
3. 最后 `crontab -l | wc -l` + 关键行 grep 双重验证

改完立刻把服务器 crontab 备份一份到 `/tmp/cron_bak_YYYYMMDD.txt`。

**生产 chip 口径**：WorkBuddy 本地拉东财真实 CYQ 筹码 → 批次文件
`_chip_batch_{NN}_{YYYYMMDD}.json` → `_upload_chip_{YYYYMMDD}.py` 合并上传。
上传前必须跑 `check_chip_batches.py --date YYYY-MM-DD`，不通过禁止上传。

## 历史教训（为什么必须有这些）

| 日期 | 事故 | 根因 | 防线 |
|------|------|------|------|
| 08-24 | K 线 08-24 仅 960/4991 | 服务器 fix_kline 是旧版 WORKERS=16，16 并发触通达信限流 | 串行 + 覆盖率门槛 |
| 08-24 | chip 1192 只停 08-21 | WorkBuddy 批次缺 18/19（400只）+ 其他缺口，照常上传；服务器旧数据保留 | 上传前批次校验 + 18:15 复查 + readiness 覆盖率检查 |
| 08-24 | 04:50 闸门没拦住 | chip 检查用「众数日」对照，半截数据众数是 08-24 误判通过 | 改为「最新日覆盖率 ≥95%」 |
| 08-24 | 覆盖率告警无人理会 | freshness/daily_coverage 只写日志，无行动链 | daily_coverage 挪 18:15（WorkBuddy 上传后）+ chip_missing_alert 写 data_alerts |
