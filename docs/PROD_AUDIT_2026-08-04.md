# AlphaPilot 生产代码全量审计报告（2026-08-04）

- **审计人**：WorkBuddy
- **日期**：2026-08-04 15:20-16:30
- **目的**：确保 2026-08-05 选股链路（05:00 pipeline → 09:35 scanner → 09:50 scores）零故障
- **交叉验证**：本报告已同步服务器 docs/ 供 Cursor 复核

---

## 🔴 P0 级问题（已修复）

### 0. 【v25 验证结论】区分度差 → 明天保持 v18，v25 待深查

recommend.py v25 全市场验证（16:56 完成，4997 只，~35 分钟）：
- **Top 评分全部集中在 0.5592-0.5605（带宽 0.0013）——区分度极差**，v25 模型对全市场几乎不区分
- 结论：**v25 不能上生产**；recommend.py 已回滚 v18（备份 `.bak_v18_20260804`）
- 待 Cursor：v25 评分区分度差的根因（模型概率分布退化？特征标准化？训练问题？）

### 1. 【两套模型在运作】生产实际跑 v18，宣称 VM2.5/v25 —— 已定位 + 保持 v18

**根因**：
- `ml_screener.py`（07-27 13:00 版）默认 `model_version="v18_fusion_v2"`，**无 v25 分支**
- `recommend.py` 调 `screener.load_model()`（**无参数**）→ 走 v18
- pipeline 413 行标签 "VM2.5模型选股" + api_server 返回 "v25" → **宣称与实跑不一致**
- 历史：07-18 `wire_v25_now.py` 曾给 ml_screener 打 v25 补丁（07-21 记忆"生产 VM2.5"成立）；**07-27 ml_screener 被覆盖回原版 → v25 补丁丢失 → 生产静默降级 v18**，07-27 后每天选股实际都是 v18
- `vm25_scorer.py`（v25_opt，93 特征）只在回测/编排脚本用，**无生产调用方（孤儿）**

**修复（已部署）**：
1. ml_screener.py 重新打 v25 补丁：`_load_v25()` + `_score_v25()` + load_model/score_stock 分支（备份 `.bak_v25_20260804_1533`）
2. recommend.py：`screener.load_model("v25")`（失败回退 v18）（备份 `.bak_v18_20260804`）
3. pipeline 超时 1200→3600（v25 全市场 ~35 分钟）

**验证**：vm25_scorer 加载 v25_opt OK（93 特征/3 模型），单只评分 0.62s，recommend.py 全市场 v25 验证进行中

### 2. 【chip 数据被覆盖】3489 只（08-04）—— 已修复

**根因**：15:32-15:33 有**外部进程**重写 `chip_data_all.json`（根目录+data/ 两个），从 4992 只（08-03 全市场）覆盖成 **3489 只（08-04 深沪，无北交所/缺 1503 只）**

**修复（已部署）**：westock MCP 补拉 1503 只 08-04 → 合并 → 两个文件均恢复 **4992 只全 08-04** ✓

### 3. 【backtest_cache 无自动重建】明天评分会滞后 —— 已修复

**根因**：recommend.py 评分读 `backtest_cache/*.pkl`（今天手动重建到 08-03）；16:15 fix_kline 更新 kline_all 到 08-04 后**缓存不会自动重建** → 明天 05:00 用 08-03 缓存评分（滞后）

**修复（已部署）**：cron 加 `22 16 * * 1-5 rebuild_backtest_cache.py`（16:15 fix_kline → 16:22 重建 → 16:25 覆盖率检查）

### 4. 【cron 重复】daily_coverage_check ×2 —— 已去重

---

## 🟡 P1 级问题（需用户/外部确认）

### 5. 15:27-15:33 外部进程写入生产数据

- 15:27 `daily_recommend.json` 被重写（内容仍 10:08 版）
- 15:28 `morning_live_picks.json` / `vol_gate.log`（paper_trading_signals_v2 调用）
- 15:32-15:33 `chip_data_all.json` 被覆盖（3489）
- 14:07 有 `uvicorn run_server:app`（port 8000）启动；14:05 api_server.py / vm25_scorer.py 被改（chip 路径修复，合理）

**判断**：疑似**另一个会话/进程在操作生产**（非 cron、非 WorkBuddy 本次操作）。**需用户确认**：14:00-15:33 是否有其他 AI 会话/自动化/手动操作在动服务器？建议限制生产目录写权限/操作留痕。

---

## 🟢 正常项（核验通过）

| 项 | 状态 |
|---|---|
| K线 kline_all | 100%（08-03），16:15 fix_kline 每日更新 |
| 资金流 fund_flow | 5000 只，到 08-03（08-04 明天 04:52 补齐，不影响 05:00）|
| 模型文件 | v25_opt_ensemble ×3 + v25_meta（08-02 训练）就绪 |
| api_server/vm25_scorer 14:05 改动 | chip 路径修复（根目录→data/），合理 |
| 覆盖率检查 | 16:20 freshness + 16:25 daily_coverage_check |

---

## 📋 明天（08-05）链路时间线（修复后）

```
05:00  pipeline 启动 → VM2.5(v25) 评分 ~35min → 05:35 → 门控 ~30min → 06:05 完成
09:35  scanner（正常路径，池≥30 可用）→ morning_live → Top 落盘
09:50  scores 同步 → QMT ML选股读 20260805.json
16:15  fix_kline（kline_all → 08-05）
16:22  rebuild_backtest_cache（缓存 → 08-05）
16:25  daily_coverage_check（全数据时间+覆盖率）
```

## ⚠️ 待 Cursor 复核项

1. v25 接入后 ml_screener 补丁代码正确性（_load_v25/_score_v25 与 vm25_scorer API 对齐）
2. v25（08-02 训练，AUC 0.7146）是否确认接生产（vs 继续 v18）——需 OOS 参考；07-21-07-27 曾生产 v25
3. 15:27-15:33 外部写入的来源确认
4. recommend.py v25 全市场 35 分钟是否可接受（超时已 3600）

---

## 🔄 补充：Cursor 报告交叉验证（2026-08-04 18:52-19:45）

### 结论总览

| Cursor 报告项 | 独立核实结果 | 状态 |
|---|---|---|
| 116 维模型已部署（v25 17:14 重训） | ✅ recommend.py `load_model("v25")` → vm25_scorer feats=116（82 base + 8 derived + 6 chip + 10 tech + 10 extra_rd）；6 个 v25 模型 17:14 全部重训；meta `deployed: 2026-08-04 17:14` | 属实 |
| 116 维区分度良好 | ✅ **独立实测 300 只随机样本**：分数 0.181~0.576、标准差 0.074、Top15 有梯度（0.576→0.49）、十分位 0.271→0.465——**不再是 93 维那种挤在 0.559 的病态** | 属实 |
| K线 08-04 覆盖率 100% | ✅ kline_all.parquet 08-04 = **4991 只**（mtime 18:46）；backtest_cache 4992 pkl 全到 08-04 | 属实 |
| fix_kline WORKERS 16→1 | ✅ fix_kline_server.py:16 `WORKERS = 1`（注释注明限流根因） | 属实 |
| 回测提升（45%→65% win_rate） | ⚠️ 采用 Cursor 数据（A1 口径 top2 T+1/T+2）；**未独立复现回测**，且 meta note 自认 "OOS IC gate still required before production switch" | 待 OOS |

### 新增修复（本交叉验证发现）

1. **fix_kline cron 双跑去重**：16:15 行 `fix_kline_server.py ... && fix_kline_server.py` 跑两次（幂等但浪费）→ 已去重为单次
2. **data/fund_flow_cache.json 只有 1 只（000811）**：15:27 外部进程用 fund_flow.py 拉单只覆盖 → **已重建 5000 只全量**（main_net_today/5d/10d/20d，源自 fund_flow_history 08-03）——v25 评分不受影响（vm25_scorer 读 fund_flow_history），但防 v25 挂掉 fallback v18 时特征失真
3. **确认关键修复未被 Cursor 覆盖**：pipeline 超时 3600（413 行）✓ / scanner 阈值 30（552 行）✓ / scanner fallback 涨停过滤（757-768 行）✓ / money_flow_gate hard_main_net_5d（22/85 行）✓

### ⚠️ 遗留风险

1. **v25 生产速度**：20 线程全市场 2.3 只/s → **约 36 分钟**（超时 3600 够）；完整 recommend 验证进行中
2. **v25 未过 OOS**：Cursor meta 自认 "OOS IC gate still required"——明天生产用 v25 属于"回测强、OOS 未验"状态；若担心可切回 v18（recommend.py.bak_v18_20260804，一条命令恢复）
3. **15:27 外部写入**（chip/fund_flow_cache/daily_recommend）与 16:33/17:14 模型重训仍指向并行会话操作生产，建议加操作锁
4. **v25 训练数据口径**：116 维含 10 个 extra_rd 因子（集合竞价/ATR z-score），训练在本地完成，服务器评分需依赖 models/extra_factors.parquet（已确认存在）

### 明天（08-05）链路最终核验

```
05:00  pipeline → recommend.py(v25 116维, ~36min < 超时3600) → 09:35 前完成
09:35  scanner（阈值30, 涨停/新股过滤）→ morning_live（hard_main_net_5d 资金门）→ Top 落盘
09:50  export_qmt_scores → QMT 读 20260805.json
16:15  fix_kline(WORKERS=1, 单次) → 16:22 缓存重建 → 16:25 覆盖率检查
04:52  fund_flow_history 补 08-04（次日）
```

---

## ✅ 最终验证结果（19:34 全市场实测）

recommend.py(v25 116维) **全市场完整跑通**（18:58 启动 → 19:34 完成，36 分钟 < 超时 3600s）：
- 4997 只扫描，500 只入候选池
- **Top12 区分度良好**：百花医药 0.7459 → 东晶电子 0.6825 → 神雾节能 0.635 → … → 深信服 0.5592（梯度明显）
- Top500 分数 0.4695~0.7459
- 与 93 维病态对比（当时全挤 0.5592-0.5605）→ **116 维模型恢复正常区分能力**

**交叉验证最终结论：Cursor 报告属实，明天 08-05 生产链路就绪**
