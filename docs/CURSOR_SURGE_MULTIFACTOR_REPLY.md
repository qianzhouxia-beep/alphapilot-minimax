# Cursor 回复：涨停多因子研究 → B 臂接入

日期: 2026-07-23  
对象: WorkBuddy / 钱多爸  
依据: `output/surge_multi_factor_report.md`（第四节权重 + 第五节落地方案）

---

## 1. 对研究结论的态度

**同意主结论**：涨停前最可靠的是「资金埋伏 + 板块共振」，K 线前置形态弱。这和我们已定的分轨一致——万得/资金走咨询与 B 臂软分，不靠均线多头硬捞 77.7%。

| 发现 | Cursor 判定 |
|------|-------------|
| 连续净流入 ≥3 天最佳平衡（1.38x） | 采纳为 B 臂主因子 |
| fresh_inflow 板块共振（电网设备验证） | 已有 `wind_sector_prefer_boost`，可加强 |
| 54% 回锅肉动量 | 可接，但要防追高（连板次日更脆） |
| 早盘首封 / 封板资金比 | **盘中确认**，不进 05:00 日频打分 |
| K 线弱 | 维持：B 臂不加均线/量比硬门槛 |

---

## 2. 第四节权重 vs 第五节打分 —— 先对齐口径

第四节是「解释性权重表」；第五节是「可执行 0–10 分」。生产应以**第五节打分为准**，第四节作审计说明，避免两套数字打架。

建议生产映射（只打 `arm=B`）：

| 报告因子 | B 臂实现 | 现状 |
|----------|----------|------|
| ① 连续净流入天数 | 个股 `consec_inflow_days` → 埋伏分 | ❌ 缺（现有 `fund_pos_days_5` 是 5 日窗口计数，非连续） |
| ② 机构今日净买入 | `wind_candidate_flow.inst_net` | ✅ 已有软分 +0.02；要升成埋伏分 |
| ③ 板块 fresh_inflow | `wind_sector_prefer_boost` | ✅ prefer×1.05；建议并入埋伏总分后统一乘子 |
| ④ 近期多次涨停 | ak/涨停池近 N 日命中 | ❌ 缺 |
| ⑤⑥ 封板时间/质量 | 仅 09:35+ 盘中 / trade_precheck | ❌ 不进日频 B 臂 |
| ⑦ 60 日新高 | 可选弱加分 | 低优先 |

第五节乘子建议微调（与现有 ×0.85 底座兼容）：

```
底座: arm=B → score × SURGE_ARM_B_MULT(0.85)

埋伏总分 S (0–10):
  ≥7 → 再 ×1.15   → 有效约 0.85×1.15 ≈ 0.98（接近 A 臂，仍略弱）
  4–6 → 再 ×1.05  → ≈ 0.89
  <4  → 不再乘    → 保持 0.85

禁止: 日频用封板质量抬分（没有盘前数据，会空转）
```

---

## 3. 接入位置（管线顺序）

保持 A 臂不动。只在 B 臂软链路上加一层：

```
宇宙门 → arm=A|B
资金门: A=硬门 / B=soft_intraday
wind_sector_prefer_boost     ← 可保留，或并入下面埋伏模块（二选一，防双重计分）
★ NEW: surge_ambush_score    ← 只处理 arm=B，写 surge_ambush_* 字段 + 乘子
旁路出货硬拒 / nuclear …
```

**防双重计分**：若开 `surge_ambush_score`，则关闭或降权 `wind_sector_prefer_boost` 里的 prefer 项（板块分已算进埋伏总分），avoid 降权可保留。

---

## 4. P2 建议拆票（Cursor 可开工）

### P2a — 个股连续净流入天数（阻塞）

- 数据：`fund_flow_history`（或通达信/东财日资金）按码回溯，算 App 口径连续天数  
- 写入候选：`consec_inflow_days` + `consec_inflow_src`  
- Wind 4 档有则优先标 `inst_net`，天数仍可用本地历史（Wind 积分不够扫全池历史）

### P2b — `surge_ambush_score.py`（核心）

- 输入：B 臂 items + wind_board_flow + wind_candidate_flow + （可选）近 N 日涨停集合  
- 输出：`surge_ambush_score` / `surge_ambush_tier` / `score` 乘子  
- Env：`ENABLE_SURGE_AMBUSH=1`（默认关，Watch 一周再默认开）

### P2c — 动量（近期涨停）

- 日更涨停池缓存；近 10 交易日命中 → +2 分  
- 今日已涨停不可买的仍由现有近涨停硬门处理

### P2d — 盘中封板（非日频）

- 11:35 / 14:25 后：若候选在今日涨停池且首封&lt;10:00 且封比&gt;1% → trade_precheck 或 EOD 软确认  
- **不进 05:00 打分**

---

## 5. 需要 WorkBuddy 确认的 3 个问题

1. **连续天数数据源**：生产用本地 `fund_flow_history` 算连续天数，Wind 只补机构分档——是否同意？（积分友好，与报告回测同源）  
2. **prefer 双重计分**：开埋伏总分后，是否关掉 `WIND_B_PREFER_MULT`，只留 avoid？  
3. **默认开关**：P2b 先 `ENABLE_SURGE_AMBUSH=0` Watch 5 个交易日，还是直接默认开？

---

## 6. 明确不做

- 不把 K 线多头/量比做成 B 臂硬门槛  
- 不用封板质量做盘前选股（无数据）  
- 不把埋伏分塞进 A 臂硬门（A 臂继续保胜率）  
- 不因 1.38x 就把 ≥3 天连续流入做成全市场硬捞（那是扩大 CACHE，碰 77.7% 上限区）

---

## 7. 一句话回 WorkBuddy

> 权重表采纳，落地以第五节 0–10 分为准；P2 先补**个股连续净流入天数** + **B 臂埋伏软乘子**，板块 prefer 并入总分防双计；封板质量只做盘中确认。请确认上面 3 个问题后 Cursor 开工 P2a/P2b。

---

## 8. 落地状态（2026-07-23 夜）

三问全同意后已开工并上 VM：

- `consec_inflow.py` — fund_flow_history App 口径连续天数  
- `surge_ambush_score.py` — B 臂埋伏分；`ENABLE_SURGE_AMBUSH=0` Watch  
- `wind_sector_prefer_boost` — ambush apply 时 prefer 乘子关，avoid 留  
- 文档：`docs/P2_SURGE_AMBUSH.md`  
- Smoke：`python3 -u scripts/smoke_surge_ambush.py` ✅

Watch 盯日志 `surge_ambush: apply=0 …` 与 `daily_recommend.surge_ambush`；5 个交易日无异常再开 `ENABLE_SURGE_AMBUSH=1`。
