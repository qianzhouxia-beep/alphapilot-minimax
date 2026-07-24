# P1：ENABLE_SURGE_ARM_B 扫漏软回流

日期: 2026-07-23  
核准: 钱多爸（只打 20.8%；77.7% 作上限）

---

## 行为

| Env | 默认 | 含义 |
|-----|------|------|
| `ENABLE_SURGE_ARM_B` | **1（开）** | 非启动∪旁路 → `arm=B`，分数 ×0.85，进池 |
| `SURGE_ARM_B_MULT` | `0.85` | B 臂降权 |
| 回滚 | `ENABLE_SURGE_ARM_B=0` + `ENABLE_SOFT_UNIVERSE=0` | 恢复启动\|旁路硬删 |

资金分轨：

- **臂 A**（启动 / 旁路）：`money_flow_gate`（现状）
- **臂 B**：`soft_intraday_gate` 软加权，**不硬删**
- 近涨停补位、下跌通道、nuclear：仍硬（全臂）

模块：`soft_universe_gate.py` + `alphapilot_pipeline_v3.apply_money_gate`  
产物：`daily_recommend.json` → `pipeline_version=v3.4_surge_arm_b`，含 `surge_arm_b` / 每票 `arm`

---

## 验收（Watch）

对照子集：**曾进 ML Top500 且 T+1≥5%**（不要用 77.7% 全样本刷脸）

| 指标 | 看什么 |
|------|--------|
| 臂 B 进池占比 | 日志 `armB=` / JSON `surge_arm_b.n_arm_b` |
| Top2 中 arm=B 占比 | 是否偶发抢戏（过高则降 MULT） |
| hit≥5% / 成交率 / maxDD | vs 开启前 1–2 周 |

回滚一行：

```bash
ENABLE_SURGE_ARM_B=0 ENABLE_SOFT_UNIVERSE=0 python3 -u alphapilot_pipeline_v3.py
```

---

## 与 SoftUniverse

SURGE 开时覆盖旧 `soft_universe` 标签（mult 从 1.0 改为正式 0.85 + `arm=A|B` + B 资金软门）。
