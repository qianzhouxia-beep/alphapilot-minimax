---
project: alphapilot
domain: data
title: K 线兜底源事实：新浪不复权(主,带 amount) + 腾讯 gtimg(WAF 501 会封 IP)；TDX 单源事故已加固
date: 2026-09-11
status: conclusion
tags: [kline, 数据源, 兜底, 新浪, 腾讯gtimg, westock, WAF, 可靠性]
source_chat: 老板拍板"方案三全做"→ Cursor 实现并实测
---

# K 线多源兜底：源事实与坑（2026-09-11）

> 背景：09-10 TDX 服务端协议级中断，`fix_kline_server.py` **0/4991** 空跑 5h18m → K 线单源依赖坐实为管线最大脆点。
> 实现：`production_strategies/server/fix_kline_server.py`（已部署服务器，cron 16:15）。
> 关联：`knowledge/data_sources/2026-09-11-kline-0910-recovery.md`、`westock.md`。

## 1. 源对比（实测）

| 源 | 复权 | volume 单位 | amount | outstanding_share/turnover | 全市场实测 | 备注 |
|---|---|---|---|---|---|---|
| **TDX (mootdx)** | 不复权 | 手（脚本内自适应×100） | 有 | **无**（需沿用旧值） | 正常时 100%；09-10 起 0% | 主源，单一 |
| **新浪 `adjust=""`** | **不复权** | **股** | **有** | **有** | **4982/4991 = 99.8%** | **兜底主源**；生产 `data_fetcher` 即走新浪 |
| 腾讯 gtimg `day` | 不复权 | **688=股 / 其余=手** | **仅最新日**（qt 串） | 无 | 首轮 2109/4991 后被封 | **WAF 501 封 IP**，仅备源 |
| 腾讯 gtimg `qfqday` | **前复权** | 同 | 无 | 无 | — | ❌ 前复权滞后一天，**不可用于本管线** |
| westock (本地 CLI) | 不复权 | 688=股/其余=手 | 有 | — | 09-10 手工救急用过 | 仅 Mac 侧，服务器不可用 |
| baostock | 可选 | 股 | 有 | — | **服务器未安装** | 本次未采用 |

## 2. 三个硬坑（都已在代码里处理）
1. **腾讯前复权 qfq 滞后一天** → 必须用不复权 `day`，否则价格基准与缓存不一致。
2. **腾讯 WAF 限流**：无节流跑 ~5000 请求后，服务器 IP 被腾讯 **HTTP 501** 整机封禁（curl/python 同样 501）。
   - 解法：腾讯降为**备源** + 全局限速（`FB_MIN_INTERVAL=0.05s`，~20 req/s）+ 多轮冷却重试。
   - 实测：新浪路径 500/57s、1500/155s，成功 1498/1500，稳定 ~10/s。
3. **单位/口径不可信就宁可不写**：逐行 `amount/(volume×close) ∈ [0.8,1.2]` 校验；停牌股（无目标日行）跳过。
   - 09-10 那"缺失 10 只"经查**多为停牌**（如 600929 最后交易日 08-28），非数据丢失。

## 3. 覆盖率闸门（安全底线）
- TDX 覆盖 <90% → 触发兜底；兜底后仍 <90% → **拒绝写入**（绝不用残缺数据覆盖缓存）。
- 09-11 第一版纯腾讯兜底只到 42.3% → 闸门正确拒写 ✅（日志 `fix_kline_dryrun_0911.log`）。
- 新浪版 → 99.8% ≥90% → 放行 ✅。

## 4. 仍未做/待办
- **baostock 未安装**（用户方案原列了它）→ 现由新浪替代；如要三源可 `pip install baostock` 后补 `fetch_one_baostock`。
- **腾讯 IP 封禁会自解**（WAF 临时），但不宜再高频用。
- 09-10 缓存仍缺 9 只（多停牌）；如需强制 backfill，可手动 `python3 fix_kline_server.py --skip-tdx`（**注意会以新浪值覆盖全市场当日行与 outstanding_share/turnover**，建议先备份评估）。
- `extra_factors` 新鲜度已纳入 `data_readiness_gate`（`extra_factors_asof`）。
