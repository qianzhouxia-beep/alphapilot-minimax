# Cursor 审计结论：B 臂资金门候选

日期: 2026-07-23  
回应: WorkBuddy 六问第 5 条  
状态: **已完成审计**

---

## 结论（一句话）

| 模块 | 能否直接当 B 臂资金门 | 说明 |
|------|----------------------|------|
| `soft_intraday_gate.py` | **能** | 已是软加权、不删票；生产里默认关，可用 `ENABLE_SOFT_INTRADAY=1` 或仅对 `arm=B` 调用 |
| `weak_fund_sleeve.py` | **不能直接当门** | 这是 nuclear 日独立「研究袖套选股」，不是对候选列表做门控；勿硬套 |

---

## soft_intraday_gate — 适合 B

- 读 `data/intraday_soft_gate.json`（东财排名/净流入 + 行情）
- 只做 `score += bonus`，**零硬删**
- 已在 `alphapilot_pipeline_v3.py` 挂好，现默认关闭（保 A 臂）
- **P1 建议**：A 臂保持现状；B 臂回流票强制走 `apply_soft_intraday_gate`（可不依赖全局 env，或仅 B 子集调用）

与万得关系：东财软分 + 万得盘中 B′ 软确认可叠加；万得仍不进 hard avoid。

---

## weak_fund_sleeve — 不适合当门

- 入口是 `scan_weak_fund_sleeve(asof)`：全市场按行业聚合资金 → 挑 sustained_in → TopN
- 设计场景：**主臂 nuclear 空仓时的小仓研究臂**，默认不自动下单
- 与「对已有 Top500 回流票做资金软门」不是同一抽象

可选后用（非 P1）：把袖套选出的票标 `arm=B_sleeve` 并入扫漏池——需单独设计，**不是**把 sleeve 函数塞进 money_gate 位置。

---

## 给 WorkBuddy / 钱多爸

P1 资金侧最小实现：

```text
臂 A：现有 money_flow_gate（硬/弱硬按现状）
臂 B：软回流后 → soft_intraday_gate（东财）→（可选）Wind B′ 软标签加分
弱资金袖套：暂不动；P2 再议是否并入 B 源
```

钱多爸拍板「核准双轨 + Wind 盘中优先」后：
1. WorkBuddy 继续跑 P0 `diagnose_surge_death.py`
2. Cursor 等 P0 表出来再改 pipeline 软回流（带 feature flag）
