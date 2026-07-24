# P2：涨停埋伏分（连续净流入 + B 臂软乘子）

日期: 2026-07-23  
核准: WorkBuddy 三问全同意 → Cursor 开工

---

## 行为

| Env | 默认 | 含义 |
|-----|------|------|
| `ENABLE_SURGE_AMBUSH` | **0（关）** | Watch：写 `surge_ambush_*` / `consec_inflow_days`，**不改分** |
| `=1` | | 按 tier 乘分；同时关掉 `WIND_B_PREFER_MULT`（防双计），保留 avoid |

| tier | 总分 | 乘子 |
|------|------|------|
| strong | ≥7 | ×1.15（`SURGE_AMBUSH_STRONG_MULT`） |
| mid | 4–6 | ×1.05 |
| plain | <4 | ×1.0（保持 B 底座 0.85） |

打分（只对 `arm=B` 乘分；A 臂只注解天数）：

- 资金 0–5：连续≥4→+3 / ≥3→+2；机构净买→+2；机构+大户→+1  
- 板块 0–3：Wind prefer→+2；`data/zt_sector_top.json` Top→+1（可选）  
- 动量 0–2：`data/zt_recent_codes.json` 近涨停→+2（可选）

连续天数：`consec_inflow.py` ← `data/fund_flow_history.json`（App 口径，与回测同源）。

---

## 管线位置

```
宇宙门 → 资金门(A硬/B软) → wind_sector_prefer_boost → ★ surge_ambush_score → …
```

模块：`consec_inflow.py` + `surge_ambush_score.py`  
产物：`daily_recommend.json` → `surge_ambush` 摘要；`pipeline_version=v3.4_surge_arm_b`（Watch）/ `v3.5_surge_ambush`（apply）

---

## Watch 5 日（当前）

盯：

- 日志 `surge_ambush: apply=0 B=… strong=… mid=… plain=…`
- JSON `surge_ambush.watch_mode=true` 与字段分布
- Top2 中 arm=B 占比是否异常（Watch 期不应因埋伏分漂移）

开乘子：

```bash
ENABLE_SURGE_AMBUSH=1 python3 -u alphapilot_pipeline_v3.py
```

或在 cron/env 文件里持久打开。

---

## 可选数据文件

| 文件 | 作用 |
|------|------|
| `data/zt_recent_codes.json` | 近 N 日涨停码 → 动量 +2 |
| `data/zt_sector_top.json` | 涨停行业 Top → 板块 +1 |

缺失则该项记 0，不阻断。

---

## Smoke

```bash
python3 -u scripts/smoke_surge_ambush.py
```
