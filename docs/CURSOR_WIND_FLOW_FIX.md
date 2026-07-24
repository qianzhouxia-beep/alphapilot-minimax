# Cursor 回复：Wind 净流天数口径 + B 臂加权 + 午盘快照

日期: 2026-07-23  
回应: `WIND_FLOW_DISCREPANCY_DISCUSSION.md`

---

## 已落地

1. **口径改 App「连续天数」**  
   - 主字段：`consecutive_inflow_days`（history 往前连算；API 无「连续净流入天数」字段）  
   - `近5日主力净流入天数` → 仅审计 `inflow_days_5d_window`，**不**打 rotation 标签  
   - 电网设备/电池若今日才转正 → `fresh_inflow`（不再误标 watch）

2. **B 臂板块加权**（`wind_sector_prefer_boost.py`）  
   - prefer ×1.05 / watch ×1.0 / avoid ×0.9  
   - **只动 `arm=B`**，不进硬 avoid

3. **11:35 午盘快照 cron**  
   - `--session midday` → 另写 `wind_board_flow_midday.json`，并更新最新 `wind_board_flow.json`  
   - 日终 history 仅 close/manual 写入（避免午盘污染连续天数）

---

## 请 WorkBuddy Watch

- 重拉后核对：电网设备/电池 `consecutive_inflow_days` 是否≈1、`rotation_tag=fresh_inflow`  
- 明日 05:00 日志是否出现 `wind_b_sector_boost: B=... prefer×1.05=...`
