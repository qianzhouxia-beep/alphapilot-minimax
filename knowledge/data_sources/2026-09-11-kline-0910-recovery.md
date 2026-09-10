---
project: alphapilot
domain: data
title: 09-10 K线缺口事故与恢复（TDX 服务端中断 → 老板拍板"方案二"腾讯/westock 单日合并，三重校验）
date: 2026-09-11
status: conclusion
tags: [数据质量, K线, TDX中断, fix_kline, 缺口恢复, 原子写入, 5m缺口]
source_chat: WB 报告事故 → 老板拍板方案二 → Cursor 复核确认
---

# 09-10 K 线缺口事故与恢复（Cursor 01:30 复核）

## 一、事故（WB 发现）
- `fix_kline_server.py`（cron 16:15）**全失败 0/4991**，跑了 **5h18m**（19067s）后 `[ERR] 全部拉取失败, 未写入`；
- 同期 `build_kline5m.py`（16:20）**0 只 / 0 行**（同源 mootdx/TDX）；
- ⇒ 缓存 `max=2026-09-09`，**09-10 整天缺失**；
- **下游受损**：`rebuild_extra_factors`（21:20 跑）日志「日期止于 2026-09-09」⇒ **05:00 管线的 RD 因子少一天**；
- 根因与 09-10 白天结论一致：**TDX 服务端协议级异常，非 IP 封禁**（WB 跨网复现），**未自愈**。

## 二、恢复（老板 2026-09-11 拍板「方案二」）
服务器脚本 `/tmp/_merge_kline_0910_server.py`（WB 执行，**非 Agent 擅自写库**）：
- 输入：本地 westock 拉的 09-10 日线 CSV（volume 已换算为**股**）；
- 动作：**备份 → 追加 09-10 行 → 三重校验 → 原子写入 `data/` 与根目录双路径**；
- **三重校验**：覆盖率 ≥95%、单位 `amount/(vol×close) ∈ [0.8,1.2]`、日期纯净；**历史行数必须逐日不变**（否则 abort）；
- **校验不过 = 不写入**（宁可不写）；幂等（已存在即退出）。

**结果**：
```
kline_all.parquet:         max=2026-09-10  rows=2,025,911  (+4,981)
data/kline_cache:          max=2026-09-10  rows=2,025,911
备份: data/kline_cache/kline_all.parquet.bak-0911（57,510,463 B）+ 根目录同名 .bak-0911
```
**可信度**（Cursor 独立抽验）：`002636 C=76.45` / `600519 C=1285.13` / `000001 C=11.85` —— 与 WB 早先腾讯探针**逐一吻合**；单位比 `amount/(vol×close)≈1`（=股，过铁律）。

**10 只无 09-10 行**：`002870/002998/301390/600825/600929/603159/605577/688291/688432/688981` —— 大概率**停牌**（覆盖率 4981/4991=99.8%，过 95% 门）。

## 三、Cursor 已补的下游
- ✅ **重跑 `rebuild_extra_factors.py`**（输出 `models/extra_factors.parquet`，**上次停在 09-09，05:00 管线输入**）；已确认读到 `K线 2025-01-02 ~ 2026-09-10`，约 11 分钟，自动备份旧文件。
- ⚠️ **5m 09-10 仍未补**：`build_kline5m.py` 走 mootdx，TDX 不通 → **需腾讯 m5 另写**（只影响 P2/G1 影子与 sim 出场研究**仅 09-10 一天**，**不阻断 05:00 选股**）。
- ⚠️ **chip 仍停 09-08** → readiness `chip_asof` **FAIL**（kline 09-10 vs chip 09-08，缺口 2 天）——**WB 上传线**，等自愈。

## 四、待办
1. **5m 09-10**：定是否腾讯 m5 补（不急）；
2. **chip 09-09/09-10**：等 WB 上传自愈，否则 readiness 持续 FAIL；
3. **`fix_kline` 自愈**：外部 TDX 恢复后，20 日窗口会自动补 09-10（届时注意别与手工行重复——脚本幂等，但 `sync_kline_root` 仍建议核对）；
4. **P1-DOWN 09-10 marker**：K 线到位后 `python3 -u rd_workshop/shadow_p1_down_daily.py --asof 2026-09-10`（**20 日内补录即可**）。

## 关联
- `knowledge/data_sources/2026-09-11-sim-ledger-buyprice-bug.md`（buy_price 根因=缓存不新鲜）
- checkpoints 2026-09-10 17:24 / 17:50（TDX 中断）· Issue#6 c5622755776
- 服务器 `output/logs/{fix_kline,rebuild_extra_factors_0911}.log`
