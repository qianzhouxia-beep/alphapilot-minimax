# 万得板块资金流 — 咨询 / 研报轨

**状态**: 已落地（与交易硬门分轨）  
**目的**: 收盘/午盘万得行业流支持咨询叙事、板块偏好解释、B 臂软加权。

---

## 口径（2026-07-23 与 App 对齐）

| 字段 | 含义 |
|------|------|
| `consecutive_inflow_days` | **主口径**：从今日往前连续主力净流入>0 天数（= Wind App「净流天数」） |
| `inflow_days_5d_window` | 审计用：近5日窗口内有几天净流入（**不**驱动轮动标签） |

轮动标签（基于连续天数）：

| 连续天数 | 标签 | B 臂软加权 |
|----------|------|------------|
| 1–2 | `fresh_inflow` → prefer | ×1.05 |
| ≥3 | `rotation_watch` | ×1.00（默认可调） |
| ≥4 | `rotation_high_risk` | 同上 |
| 当日流出 | `outflow` → avoid | ×0.90 |

---

## 分轨

| 轨 | 数据 | 用途 |
|----|------|------|
| 咨询 / 研报 | 万得行业指数资金 + 全A分档 | 主叙事、早报/午评 |
| B 臂软分 | `wind_sector_prefer_boost.py` | 只加权 `arm=B`，不硬删 |
| 交易硬门 | 东财/通达信 + 个股 B′ | 硬下单 |

---

## 排程

```cron
35 11 * * 1-5 ... fetch_wind_board_flow.py --session midday
10 15 * * 1-5 ... fetch_wind_board_flow.py --session close
```

安装：`bash scripts/install_wind_board_flow_cron.sh`

---

## 文件

| 路径 | 说明 |
|------|------|
| `scripts/fetch_wind_board_flow.py` | 拉指数 → JSON |
| `wind_sector_prefer_boost.py` | B 臂板块 prefer/avoid 软加权 |
| `data/wind_board_flow.json` | 最新快照 |
| `data/wind_board_flow_midday.json` | 午盘归档 |
| `data/wind_board_flow_history.json` | 日终净流入，用于连续天数 |

积分粗估：午+收各 ~52 次 ≈ 60–70 分/日。
