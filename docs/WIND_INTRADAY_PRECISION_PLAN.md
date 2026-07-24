# 盘中/盘前个股精度 + 指数用法 — 下一步清单

日期: 2026-07-23  
状态: 已落地部分 + 可继续增强

---

## 当前已落地的盘前/盘中精度

| 时段 | 模块 | 产出 |
|------|------|------|
| 05:00 | `alphapilot_pipeline_v3.py` + `wind_candidate_flow.json` | 日频池 Top2，B′ 覆盖持仓/池/尾盘 |
| 11:35 | `refresh_wind_intraday.py midday` | 板块+个股 B′ 刷新 |
| 14:25 | `refresh_wind_intraday.py pre_eod` | 尾盘前板块+个股 B′ 刷新 |
| 14:45 | `eod_s2_strategy.py` | 尾盘狙击，用已有 B′ 数据 |
| 15:10 | `fetch_wind_board_flow.py close` | 收盘板块历史归档 |
| 15:30 | `refresh_all_data.py` → `enrich_candidates_wind.py` | 盘后兜底 B′ |
| 09:30–14:50 | `trade_precheck.intraday_fund_confirm` | 下单前再验东财 live 资金/涨幅 |

---

## 一、盘前（05:00 前）提高个股精度

目标：让 05:00 管线启动时，`wind_candidate_flow.json` 已经是前一交易日收盘后的最新 B′，不是 stale。

### 1. 盘前预拉 B′（已部分有）

| 做法 | 成本 | 收益 |
|------|------|------|
| 04:30 再跑一次 `enrich_candidates_wind.py --limit 80` | ~48 分 | 保证美股/夜盘消息后，05:00 用的是最新收盘资金流 |
| 把 `refresh_all_data` 的 enrich 提前到 04:00 | 同一笔钱 | 早于 05:00 主流程完成，避免 05:00 链等待 |

建议：加一个 04:30 cron，只跑个股 B′，不跑板块。

### 2. 盘前隔夜情绪 + 指数

当前隔夜情绪用外盘（美股/中概），未用 Wind 指数。可以加：

- **万得全A 夜盘股指期货/期权情绪**：如果 Wind 有 A50 期货夜盘，盘前读 tone（`risk_on/mixed/risk_off`）
- **盘前板块 prefer 持久化**：收盘 `sector_research_bias.json` 已写，盘前直接读，不需要再拉万得

---

## 二、盘中提高个股精度

### 2.1 把 Wind B′ 拉得更频繁

| 做法 | 成本 | 收益 |
|------|------|------|
| 09:35 开盘后补一次 B′（持仓+今日 signal） | ~48 分 | 早盘下单前资金最新 |
| 14:25 前再加 13:00 开盘后一次 | ~48 分 | 午后开盘有变化时更新 |
| 09:35 + 10:30 + 11:25 + 13:05 + 14:25 共5次 | ~240 分 | 高频，但积分仍够 |

建议从 **09:35 + 14:25** 两次开始，其他时段用免费的东财 live 排名兜底。

### 2.2 个股字段继续扩

已在 `enrich_candidates_wind.py` 加了机构/大户/中户/散户。还可以加：

| 字段 | 作用 |
|------|------|
| 当日大单净流入/占比 | 识别主力真加仓 vs 散户追涨 |
| 近1/3日主力净流入 | 短窗口动量 |
| 主力净流入连续天数 | 个股层与板块层口径一致 |
| 量比、换手率（Wind 实时） | 替代部分东财/新浪 |

但注意：Wind `get_stock_price_indicators` 字段有限，不一定都有；需先 probe。

### 2.3 下单前用 Wind 确认

`trade_precheck.py` 现在只读东财 live；可以改成：

```
if wind_candidate_flow 里有这只票且较新(<10min):
  用 wind 的 inst_net/main_net 替代/补充东财
  机构净流入 + 主力为正 → 提高 weight
  机构流出 + 散户流入 → 降低 weight
```

这是**低积分、高精度**的改动：只打要下单的 1–2 只。

---

## 三、盘中指数怎么用

### 3.1 已用

- `wind_board_flow.json` → `all_a_sentiment.tone` → 研报/咨询
- `consult.prefer/avoid/rotation_watch` → B 臂 `wind_sector_prefer_boost`

### 3.2 还可以怎么用（按优先级）

#### A. 仓位缩放信号（最值钱）

用全A分档做盘中仓位建议：

```
机构 + 主力 同时净流入 → 仓位上限可提到 100%
机构流出 / 散户接盘 → 仓位上限降到 25% 或空仓
```

这个信号只改 `position_exposure`，不改硬门。

#### B. 板块轮动风险实时警报

- 连续净流入≥3 的板块数量突然增加 → 提醒「轮动风险高」
- 流入板块集中度 CR3 上升 → 主线明确，可加仓主线旁路

#### C. 个股验证：板块 fresh + 个股主力 > 0

下单 Top1–2 时，若其所属板块在 Wind `prefer` 且个股 `inst_net>0` → 确认信号；否则降权。

#### D. 盘中异常警报

- 全A 主力从正转负（10:00/13:30）→ 触发「谨慎交易」标签
- 当日从 `risk_on` 变 `risk_off` → EOD 狙击缩容

---

## 四、建议落地的下一步（按性价比排序）

1. **04:30 盘前 + 09:35 开盘后 B′ 刷新** — ✅ 已落地（`install_wind_intraday_cron.sh`）
2. **trade_precheck 读 wind_candidate_flow** — ✅ 已落地（缓存叠加，不额外耗积分）
3. **全A 情绪 → 仓位缩放因子**（咨询/解释用，不改硬门）— 待做
4. **板块轮动风险计数 → 标签输出到 daily_recommend.json** — 待做
5. 午后 13:05 再补一次 B′（可选）

---

## 五、积分预算

当前日耗约 200–250 分/1000。加上面 1–4 后：

| 项 | 增加 |
|----|------|
| 09:35 B′ | +48 |
| trade_precheck Wind（≤2只） | +1.2 |
| 板块 already 拉 | 0 |
| **合计** | **~250–300 / 1000** |

仍有 70% 缓冲。

---

## 六、明确不做的

- 万得扫全 A 个股资金  
- 用万得分钟级 K 线替代本地通达信  
- 把指数硬塞进 `money_flow_gate` 做 hard avoid
