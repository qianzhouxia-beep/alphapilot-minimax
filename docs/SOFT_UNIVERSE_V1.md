# SoftUniverse V1 — 方案 + 回测 + 生产实验

日期: 2026-07-23  
合流: 主人「做减法」× WorkBuddy「宇宙硬门误杀」× Cursor 可交易对照

## 生产状态（已部署实验）

| Env | 默认 | 含义 |
|-----|------|------|
| `ENABLE_SOFT_UNIVERSE` | **1（开）** | 启动\|旁路不再硬删；非宇宙票进池并标 `selection_arm=soft_universe` |
| `SOFT_UNIVERSE_MULT` | **1.0** | 非宇宙分数乘数（1.0≈回测 PureScore；改 0.72 即弱 Soft） |
| 回滚 | `ENABLE_SOFT_UNIVERSE=0` | 恢复原硬删宇宙门 |

模块: `soft_universe_gate.py`（由 `alphapilot_pipeline_v3.py` 调用）  
对照脚本: `scripts/compare_hard_vs_soft_universe.py`

仍保留硬踢：资金弱硬门、近涨停、下跌通道、nuclear 空仓、板块 dual（暂未动）。

---

## 回测摘要（2026-06-26 ~ 07-20）

| 指标 | Hard | Soft×0.72 | Pure(mult=1) |
|------|-----:|----------:|-------------:|
| 胜率 | 51.5% | 51.5% | 47.1% |
| hit≥5% | 21% | 21% | **29%** |
| 笔均收益 | +0.3% | +0.3% | **+3.2%** |
| maxDD | **-17%** | **-17%** | -22% |

→ 生产默认跟 **Pure（mult=1.0）**，因 Soft×0.72 与 Hard 下单结果相同。

脚本: `backtest_soft_universe_v1.py`  
结果: `output/soft_universe_v1_backtest.json`
