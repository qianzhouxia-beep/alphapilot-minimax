# 开盘重排门：09:35 实时资金重排序

## 问题

05:00 管线用昨日数据选出候选池。到 09:35 开盘后，实时资金数据更新，原排序可能已失效。今日实例：

| 股票 | 05:00 ML分(排名) | 09:50实时 | 机构资金 | 问题 |
|---|---|---|---|---|
| 紫金矿业 | 1.24 (#1) | **-3.93%** | **+2.3亿**(买入) | 机构趁跌狂吸，ML分未反映 |
| 洛阳钼业 | 1.18 (#3) | **-2.85%** | **-1.7亿**(卖出) | 机构出货，但排序仍在前3 |
| 三星电气 | 1.27 (#2) | **+0.45%**(唯一红) | +399万 | 抗跌+逆势，应提上来 |

**结论**: 09:35 需要一次基于实时Wind 4档资金的重新排序，不能直接用05:00的排序下单。

## 方案：09:35 开盘重排门

### 位置

```
05:00 管线 → 输出 daily_recommend.json (37只)
                    ↓
09:25 集合竞价门 → pre_market_gate.py (已实现)
                    ↓
09:35 开盘重排 → 读 daily_recommend.json
               → 拉腾讯实时行情 + Wind 4档资金 + Wind板块流
               → 重排序
               → 写回 daily_recommend.json
                    ↓
09:35 实时资金门 → morning_live_fund_select.py
                    ↓
09:36 下单 → paper_trading_signals.py
```

### 执行逻辑

输入: `daily_recommend.json` 的 `recommendations` 列表
输出: 同结构，但实时资金字段和评分更新

```
for each candidate:
  1. 取今日涨跌幅(chg_pct) — 腾讯免费
  2. 取该日机构资金净流入额(inst_net) — Wind
  3. 取该日大户资金净流入额(large_net) — Wind
  4. 取当日主力净流入额(main_net) — Wind

  # 机构逆势加仓信号
  if chg_pct < -2% and inst_net > 0:
    score × 1.12   # 跌了但机构在买 → 加仓
  elif chg_pct < -2% and inst_net < -5000w:
    score × 0.80   # 跌了机构还在卖 → 大幅降权

  # 正常情况
  elif inst_net > 0 and large_net > 0:
    score × 1.05   # 机构+大户双买入
  elif main_net > 0:
    score × 1.02   # 主力买入
  elif inst_net < -5000w:
    score × 0.90   # 机构大幅卖出

  # 抗跌加分
  if chg_pct > 0:
    score × (1 + chg_pct/10)  # 逆势上涨额外加分

  # 暴跌剔除
  if chg_pct < -5%:
    remove from list (暴跌不宜追)
```

### 排序后

Top10 保留展示。下单 Top 1-2 按新排序执行。

### 数据源

| 数据源 | 用途 | 成本 |
|---|---|---|
| 腾讯 qt.gtimg.cn | 实时涨跌幅/价格 | 免费 |
| Wind MCP 个股资金 | 4档归因(机构/大户/中户/散户) | 0.6分/次 × 前20只 ≈ 12分 |
| Wind MCP 板块资金 | 板块实时资金流向 | ~5分/次 |

### 积分优化

Wind 只打前 20 只候选的 4 档归因。后 20 只用腾讯 + 同花顺免费源。

### 文件

- `scripts/live_rerank.py` — 开盘重排实现
- cron: `35 9 * * 1-5 python3 -u scripts/live_rerank.py`
- 输出: 直接写回 `daily_recommend.json`（覆盖 pre_market_gate 的排序）

### 验收

对照 09:35 重排前 vs 重排后的 Top3，看哪个在 T+1/T+3 胜率更高。

### 今日验证

今日实际数据：
- 重排前 Top3: 三星电气(ML1.27) → 紫金矿业(ML1.24) → 洛阳钼业(ML1.18)
  - 紫金现跌 -3.93%但机构+2.3亿 → 应排第一
  - 洛阳钼业现跌 -2.85%机构-1.7亿 → 应降权
- 重排后 Top3: 紫金矿业(机构逆势+2.3亿) → 三星电气(红盘+0.45%) → 天山铝业(机构逆势+3513万)
