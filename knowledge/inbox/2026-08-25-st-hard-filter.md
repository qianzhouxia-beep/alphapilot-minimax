# ST/退市风险警示全链路硬过滤（*ST威领事故）

> 日期：2026-08-25
> 类型：事故复盘 + 风控规则
> 结论：A 股 **ST 与 *ST 严禁买入**，已全链路（服务器候选池 → 09:35 实时池 → 交易端）硬过滤。

## 一、事故经过

08-25 09:53，MT 模拟轨道 B（QMT sim）买入 `002667 *ST威领`：
99700 股 × 20.99 元 ≈ 209 万元，成交原因 `track_b_auction`。

当日 05:00 管线推荐池（34 只）里混入 **4 只 ST**：

| 代码 | 名称 | 类型 | score |
|---|---|---|---|
| 002667 | *ST威领 | 退市风险警示（带星） | 1.24（排第6！） |
| 002726 | ST龙大 | 其他风险警示 | 0.93 |
| 002620 | *ST瑞和 | 退市风险警示（带星） | 0.71 |
| 002514 | *ST宝馨 | 退市风险警示（带星） | 0.67 |

## 二、根因：三层漏洞叠加

1. **服务器候选池源头无 ST 过滤**：05:00 管线（`alphapilot_pipeline_v3.py` →
   `live_momentum_scanner.py` → `daily_recommend.json`）逐层扫描全市场，**全链路
   没有任何一处 ST/退市风险警示过滤**（`money_flow_gate.py`、`morning_live_fund_select.py`、
   `export_qmt_scores.py`、`vm25_scorer.py` 均无）。
2. **09:35 实时池照单全收**：`morning_live_fund_select.py` 把 05:00 的 34 只直接重排成
   `fullpool_live.json`，4 只 ST 原样保留。
3. **Track B 客户端盲目信任服务器**：`_live_pool_survivors` 只查板块权限不查 ST；
   `_p2_decide`（动态确认）只验证「价格站上 VWAP + 量能放大 + 当日不跌」；
   买入循环 `picked = money_pass优先 + 非money_pass也买`——`*ST威领` 资金门没过
   （`money_flow_pass=False`）但排在后面仍被买入。

**为什么说这比普通问题更严重**：*ST 是退市风险警示股，涨跌幅仅 ±5%（普通 10%），
与 Track B 的 P2 技术确认假设（VWAP/量能/10% 波动）完全不匹配，收益风险比极差，
且随时可能退市/停牌。

## 三、修复：多层防御（5 层服务器 + 8 文件交易端）

### 服务器端（源头，本次已部署）
| 层 | 文件 | 位置 |
|---|---|---|
| ① 最上游 | `alphapilot_pipeline_v3.py` | 05:00 写回 `recommendations` 前剔除 |
| ② 全市场重排 | `live_momentum_scanner.py` | 主路径 + fallback 写 `daily_recommend.json` 前剔除 |
| ③ 资金门 | `money_flow_gate.py` | `apply_money_flow_gate` 入口 `_is_st()` 硬剔除 |
| ④ 09:35 终选 | `morning_live_fund_select.py` | pool 加载后剔除（防 `tail` 回填） |
| ⑤ 导出 | `export_qmt_scores.py` | `export_fullpool_live` + `main` 保底剔除 |

### 交易端（客户端二次防护，本机归档，下次重启生效）
- **Track B**：QMT sim / QMT live / TDX — 新增 `_is_st_name()`，在
  `_p1_gate` / `_live_pool_survivors` / 最终买入循环 三重拦截
- **Track A**：QMT sim / QMT live / TDX / ptrade sim / ptrade live —
  `_load_candidates` + 买入循环剔除

### 判断规则
```python
def _is_st(rec):
    name = str(rec.get("name") or "").upper()
    return "ST" in name or name.startswith("退") or "退市" in name
```
ST / *ST / S*ST / 退市整理 一律剔除；名称缺失不误杀（客户端二次防护兜底）。

## 四、验证结果

- `_is_st` 单测 12 例全过（*ST威领/ST龙大/退市整理= True；南京港/宁德时代= False；空名= False）
- 服务器端到端：daily_recommend 34 只中 4 只 ST 全部剔除 → 资金门后 4 只（=今早正常推荐数），ST=0
- 13 个修改文件 py_compile 全过

## 五、规则沉淀（给 WorkBuddy / 后续 Agent）

> **A 股风控红线：ST（其他风险警示）与 *ST（退市风险警示）严禁买入，无例外。**
> 任何新候选池/新导出/新交易端代码，必须包含 ST 过滤；名称缺失的候选在交易端
> 一律按「继续校验，不直接信任」处理。Track A/B 双轨 + ptrade 全端覆盖。
