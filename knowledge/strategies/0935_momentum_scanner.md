# 09:35 动量扫描器（live_momentum_scanner）— 生产规则

> 状态：**生产生效** ｜ 最后更新：2026-08-28 ｜ 代码：`live_momentum_scanner.py`（服务器 `/home/ubuntu/alphapilot/`）

## 一句话

05:00 漏斗产出 **N 只（不固定）**；09:35 按 N 的大小走**两条路径之一**，再经 `morning_live_fund_select.py` 出 Top2/Top10。弱市 N 很小（如 4 只）**不是 bug**，也**不应**只在 N 只里重排或 NO_TRADE。

## 两条路径（硬性规则，Agent 不得擅自改）

| 条件 | 行为 | protocol |
|---|---|---|
| **pipeline ≥ 100** | 在 05:00 池内叠加实时资金流重排：`0.6 × 管线 z + 0.4 × 动量 z`（+ 板块 CapitalPulse 软加成） | `live_momentum_from_pipeline_500` |
| **pipeline < 100** | **涨幅 Top~1000 资金轨**：按涨跌幅降序取约 1000 只 → ICIR+动量 → 门控 → Top50 → 近涨停/ST 剔除 | `momentum_top1000_fund_flow` |

### 参数（env 可调）

| 变量 | 默认 | 含义 |
|---|---|---|
| `PIPELINE_MIN_CANDIDATES` | 100 | 低于此数走 Top1000 轨 |
| `MOMENTUM_TOP_N` | 1000 | Top1000 轨候选上限 |

### Top1000 轨数据源

1. **akshare 成功**：全量拉取 → `change_pct` 降序 → 去重 → 取前 N
2. **akshare 失败**：同花顺 THS **涨跌幅降序**分页，凑够 ~N+200 行后停止（**不是**全市场 5000 扫）

## 弱市 / 降仓

- 05:00 看的是**前几日**大盘 → 弱时 N 可以很小（8/25：4 只）、`position_exposure=0.5`
- 09:35 看的是**当日**资金与涨幅 → **仍启用 Top1000 资金轨**，不因弱市关闭
- **否决**：方案 B（N<100 → NO_TRADE / 死守 4 只 / 只在 4 只内重排）

## 与 05:00 / fullpool 的关系

- **06:30** `export_fullpool`：来自 05:00 池（Track B 09:25–09:35 竞价阶段读 `{date}.fullpool.json`）
- **09:35** scanner 写回 `daily_recommend.json`（Track A/B 终选、网页 Top2 同源）
- **09:36** `export_fullpool_live`：来自 09:35 终选池
- N<100 时 Top1000 轨与 05:00 池**可能零重叠**（8/25 实证）——这是**有意设计**（05:00 慢/严，09:35 快/看当日热点），不是 merge 失败

## 门控（Top1000 轨）

- 硬剔除：排除列表、跌超 5%、净利同比 < -50%
- 板块 prefer/avoid 软加权；启动池 +3%
- 板块分散：Top50 同板块 ≤4
- **ST/*ST/退市** 硬过滤（8/25 *ST威领 事故后全链路）
- 近涨停剔除：涨幅 ≥ 涨停价 × 0.97
- **位置闸（2026-09-06 起）**：补充渠道与 05:00 池汇合进同一 `recommendations` 后，由 morning_live_fund_select（09:35）+ export_qmt_scores（09:36）两道位置闸统一硬过滤 `up_low>0.5 & dist_hi<-0.05` → **Top1000 轨进来的高位派发票同样被拦**，不因"非 05:00 池"漏网。详见 decisions/index.md 09-06 位置闸行

## 下游链路

```
live_momentum_scanner → daily_recommend.json (recommendations Top50)
                     → morning_live_fund_select → Top2 + Top10
                     → export_qmt_scores → candidates.json / fullpool_live.json
```

`morning_live` **只读** `recommendations`，不读 `full_candidate_pool`。

## 历史事故与决策

| 日期 | 事件 |
|---|---|
| 2026-08-25 | 4 只 → 旧 `_fallback_full_scan` 全市场 1000 → 34 只零重叠；用户定案 Top1000 intentional |
| 2026-08-28 | 误删 `<100` 分支（只在 N 内重排）→ 已恢复 Top1000 并部署 |

## 关联文档

- 决策卡：`knowledge/inbox/2026-08-25-momentum-top1000-intentional.md`
- 复盘：`knowledge/inbox/2026-08-25-fallback-4-to-34-sources.md`
- 双轨简报：`production_strategies/docs/DUAL_TRACK_BRIEFING.md` §3.1a
- Agent 规则：`.cursor/rules/live-momentum-scanner.mdc`
