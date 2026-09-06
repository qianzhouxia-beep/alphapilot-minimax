# 影子/观察/监控 注册表（权威）

> **"现在有哪些影子在跑、各自攒到哪、判定门槛是什么、下次什么时候看"——只认本表。**
> 建立：2026-09-06（全量体检后）。体检/部署/新增影子后必须更新本表。
> 配套：时间点流水见 `ops/checkpoints.md`；待办 Excel `ops/open_todos.xlsx`；脚本 `bt_research/_cmp/_audit_shadows_20260906.py`（体检探针）。
> 判定基线日：2026-09-04（最近交易日）。**每新增/删除一个影子，先在本表登记，再动代码。**

状态图例：✅正常积累 ｜ ⚠️待首验证（明天首写） ｜ ⛔空转/停摆（要救） ｜ 🔶已修复待观察 ｜ 📋设计已定未写码

---

## A. 09:35 选股链旁路影子（服务器 morning_live_fund_select.py 尾段 append，只读不改分）

| 影子 | 模块 | 输出 | 首写/状态 | 判定门槛/用途 | 下次看 | 不混 |
|---|---|---|---|---|---|---|
| 资金环境四桶(mfc) | market_flow_condition_shadow | output/market_flow_condition_shadow.jsonl | 09-03 ✅ 2 行 | 弱市资金面标签×Top2，2-4 周后 T+1/T+5 | 09-07 09:36 +1 行 | — |
| Wind 央妈/量化四线 | wind_regime_shadow | output/wind_regime_shadow.jsonl | 09-03 ✅ 2 行 | 只读，永不改分改闸 | 同上 | 不是盘中 wind_board/intraday |
| weak_score(任务A, 弱市赢家画像) | weak_score_shadow | output/weak_score_shadow.jsonl | 09-03 ✅ 2 行 | 弱市 D10 只赚当天钱 → 需生产样本验证 | 同上 | 不是任务B(RD重训)不是任务C |
| live_tone 外围环境档 | live_tone_shadow | output/live_tone_shadow.jsonl | 09-03 ✅ 2 行 | defensive 档 Top2 反而最好(307日回测)待证 | 同上 | 不是 market_tone 资金门收紧本身 |
| **资金三角(hot+mild+c2)** | fund_bonus_shadow | output/fund_bonus_shadow.jsonl | **⛔09-06 补传→⚠️09-07 首写** | 曾空转 9 天(08-25~09-04 模块缺失)→已回放补偿；回放：命中任一因子 T+1 +0.92pp/T+5 +1.65pp vs 未命中；**mild 因子 T+5 反向待复核** | 09-07 09:36 后 l2_refresh.log 现 `fund-bonus shadow appended`；攒 2-4 周后逐候选 bucket 复核 | 不是已积累（要等 09-07 首写）；回放≠精确补回(候选池近似) |
| market_regime 环境区制 | market_regime_shadow | output/market_regime_shadow.jsonl | ⛔同左→⚠️09-07 首写 | 同上批补传 | 09-07 验证 | 同左 |
| sector_quality 板块软层 | sector_quality_shadow | output/sector_quality_shadow.jsonl | ⛔同左(3 skip)→⚠️09-07 首写 | 同上批补传 | 09-07 验证 | 同左 |
| **vp_factor F1/V1/V2** | vp_factor_shadow | output/vp_factor_shadow.jsonl | ⚠️09-07 首写（模块 09-04 上传） | ⚠️**enable+append 型**：V1/V2 真扣分（V1 可硬否决），F1 权重 0 只记 | 09-07 09:36 后现 `vp-factor shadow appended` | 不是纯只读（当日扣分+记录） |

## B. RD 每日双跑（rd_workshop cron，baseline vs plus 比 AUC）

| 影子 | cron | 输出 | 状态 | 判定门槛 | 下次看 | 不混 |
|---|---|---|---|---|---|---|
| 换手因子双跑 | 22:20 工作日 | rd_workshop/shadow_turnover/shadow_log.csv | ✅ 5 连正 diff(+0.0014~+0.0021)，09-02 超时缺 1 天已修复 | 连续 5-10 日 diff≥0 且稳定 → 谈纳入 | 09-07 22:20 后 CSV 第 6 行 | 不是生产重训；RD 影子非生产模型 |
| weakscore 双跑(任务B) | 00:20 周二~六 | rd_workshop/shadow_weakscore/shadow_log.csv | ✅ 3 连正(09-02/03/04, +0.0002~+0.0007) | 同上（最早 09-09 达 5 连） | 09-08 01:30 后看 CSV | 不是任务A(09:35 标签)；错峰 turnover 22:20 |
| **daily_retrain AUC 安全门** | 21:30 工作日 | output/feedback/retrain_status.json | ✅ 每日跑；08-21 起全拒(diff<-0.003) | **拒绝=正常保护**，模型冻结 08-21 (old 0.7221) | 哪天真放行（diff≥-0.003）即模型更新 | ⛔**不是故障**（rd_health 已不再把 auc_gate_rejected 当告警） |

## C. 盘后 monitor / 观察 cron（服务器）

| 观察 | cron | 输出 | 状态 | 下次看 |
|---|---|---|---|---|
| shadow_top2 主影子(RD 候选模型) | 09:35 写入 + 16:26 report | output/shadow_top2_history.jsonl（15 天）→ report.json/.md + wecom | ✅ 每日 append；报告/Excel 推送 ok=True | 攒够 8 到期日下 CAND/PROD 结论 |
| reversal 弱转强影子 | 14:50 scanner + 16:30 report | output/reversal_shadow_history.jsonl（9 天）+ reversal_shadow/{date}.json | ✅ | 满样本后再评 |
| top2_t1t5 结算 | 16:25 | output/top2_t1t5.json + report.md | ✅ 09-04 正常 | — |
| market_tone | 09:33 | output/market_tone.json（A50+CNH 档位，供 09:35 资金门收紧） | ✅ | — |
| Wind 四线日度 | 21:15 工作日 | data/wind_investor_flow_daily/{date}.json | ✅ 09-04 正常 | 盯 asof 跟到最新有文件日 |
| rd_health 健康检查 | 10:00 cron + 16:26 附带 | output/logs/rd_health.json | 🔶 09-06 修复告警链路（wecom import + auc_gate_rejected 降级），实测 RC=0 | 有真实告警应能推到企微 |
| **C1 裸突破 T+5 超额周度衰减** | 16:28 工作日 | output/logs/breakout_monitor.log（**未建**） | ⚠️ 09-07 首跑建 log | ALERT 判定 roll8≈-1.9pp 阈值 |
| **C2 Top2 T+5 超额累计** | 16:29 工作日 | output/top2_t1t5_excess.json + logs/top2_excess.log | ⚠️ 09-06 12:13 手动测试产物已存在；cron 首跑 09-07 | 周看累计超额 |

## D. 交易端 sim 只读影子（用户本地 QMT/TDX — Agent 无法覆盖，需用户复制后自查）

| 影子 | 载体 | 落点 | 状态 | 验证口令 |
|---|---|---|---|---|
| 竞价量只读 [SHADOW-CALL] | A QMT v2.38+/A TDX v2.31/B QMT v2.12/B TDX v1.20 | sim 运行日志逐行 | ⚠️ 服务器侧已就位（09-06 export/gate 部署 + 09-07 起归档）；**交易端 4 份待用户复制** | 日志现 `[SHADOW-CALL]` 行；服务器 09-07 起 `output/pre_market_archive/{date}.json` |
| B3 止损 2% 只读 | A QMT sim v2.39+ | C:/alphapilot/shadow/qmt_sim_b3_stop_shadow.json | ⚠️ v2.40 已含；待用户复制 | 触发后日志 `[SHADOW-B3]` + json 生成 |
| B1 P2 入场 5m 形态只读 | A QMT sim v2.40+ | C:/alphapilot/shadow/qmt_sim_b1_buy_shadow.json | ⚠️ v2.40 已含；待用户复制 | 日志 `[SHADOW-B1]` + json（含 dh_pct） |
| G1(weak 只买 rank1) | 未写码（regime 闸门回测唯一候选） | — | 📋 待 [SHADOW-B1] 攒 2-4 周真实 weak 样本后重判再立项 | — |

---

## 快查：09-07（周一）首验证清单

- 09:36 后：`grep "shadow appended" output/logs/l2_refresh.log` 应 **≥8 条/天**（A 组 8 影全 append：4 老 + 3 三角补传 + 1 vp）
- 09:25 后：`ls output/pre_market_archive/` 应有 `2026-09-07.json`
- 16:30 后：`ls output/logs/breakout_monitor.log output/logs/top2_excess.log` 已建
- 22:20 后：turnover CSV 第 6 行（09-07）；次晨 01:30：weakscore CSV 第 4 行
- 交易端（用户侧）：4 sim 端复制后日志现 [SHADOW-B1]/[SHADOW-B3]/[SHADOW-CALL]

## 曾空转记录（勿重蹈）

- **资金三角 9 天**（08-25~09-04）：模块本地有、未传服务器 → hook 静默 skip。→ 2026-09-06 起分工约定：**服务器上传/变更一律 Agent 直接做**（MEMORY.md）。
- **rd_health 告警每天 2 次从未发出**：wecom_push 在 scripts/ 只插了 ROOT path。→ 09-06 已修双路径。
- **RD OOS strict_pool 全空 1 个多月**（07-07~08-15）：kline volume 手/股单位 bug。→ 已修，铁律见 `docs/CURSOR_K线单位铁律_2026-08-22.md`。
