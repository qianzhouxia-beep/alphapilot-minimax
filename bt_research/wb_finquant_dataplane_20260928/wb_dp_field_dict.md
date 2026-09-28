# wb_dp_field_dict.md — fin_quant 扩展数据面字段字典（v1 · 2026-09-28）

> 数据目录：SG `~/rdagent_ws/wb_qlib_data/`（qlib bin 格式，provider 替换式）
> 覆盖：5221 只沪深 A 股 × 2023-02 ~ 2026-09-24 全历史｜口径：**不复权**
> 上游：SG `wb_research/data/kline_daily/`（生产日线）+ `wb_fields_20260928.parquet`

## A. 价量基础字段（自生产日线 dump）

| 字段 | 说明 |
|------|------|
| $open / $high / $low / $close | 不复权价（元） |
| $volume | 成交量（源站口径，板块间单位可能不同——比值型用法不受影响） |

## B. wb_auction_*（17 个）— 竞价/开盘行为族

公式口径对齐生产 `call_auction_factors.py`（SH），F4/F19 依赖 amount 列未纳入。

| 字段 | 含义 | 范围 |
|------|------|------|
| gap_pct | 开盘跳空幅度 %（open/昨收-1） | — |
| gap_abs | 跳空绝对值 % | ≥0 |
| gap_volume_ratio | 跳空量比（vol/MA5(vol)） | 0~10 |
| gap_vol_confirm | 量价确认（sign(gap)×(量比-1)，gap<0.3% 置 0） | -5~5 |
| open_atr_ratio | \|gap\|/ATR14% 相对开盘位置 | 0~5 |
| gap_premium | 溢价偏离（gap/昨日实体与 ATR 之半） | -5~5 |
| weak_to_strong | 弱转强（昨跌>1% 今高开） | 0~5 |
| strong_to_weak | 强转弱（昨涨>3% 今低开>0.5%） | -5~0 |
| stronger | 强更强（昨涨>2% 今高开>1%） | 0~1 |
| explosive_open | 爆量高开（gap 4-7% 且量比>1.5） | 0~1 |
| fake_gap | 假跳空诱多（gap>3% 且量比<0.8） | -1~0 |
| gap_momentum | 跳空×5日收益方向 | -1~1 |
| consecutive_gap | 连续跳空天数（阈值 0.5%） | ≥0 |
| volume_conviction | 量能置信度 | -2~2 |
| bull_score | 做多综合评分 | 0~1 |
| bear_score | 做空综合评分 | 0~1 |
| composite | bull-bear 综合 | -1~1 |

## C. wb_chip_*（4 个）— 筹码成本分布族

**算法**：标准换手衰减成本分布（CYQ）。每日筹码分布 = 昨日×(1-换手) + 当日三角核（low~high 峰值在 close）。
**标定假设**：无流通股本 → 有效换手 = vol/median(vol)×1%（即中位日换手 1%）。这是**代理口径**，与生产 Zeabur 真实筹码（人工上传快照）不同源；agent 挖出的筹码因子迁生产前须在真实筹码上复验。

| 字段 | 含义 | 范围 |
|------|------|------|
| profit_rate | 获利盘比例 %（成本<今收的质量占比） | 0~100 |
| cost_gap | 平均成本/今收-1 %（负=市场处于获利状态） | — |
| conc90 | 90% 筹码集中度（(P95-P5)/P50×100） | — |
| conc70 | 70% 筹码集中度（P85-P15）/P50 | — |

## D. 基准指数（合成）

`SH000300` = 全池等权日收益合成指数（2023-02-03=1000，09-24 收于 1134.5）。**非真实沪深300**，仅作 backtest 基准参照。真实基准数据接通前，超额收益解读需谨慎。

## E. 实验窗（.env QLIB_QUANT_*）

| 段 | 区间 |
|----|------|
| train | 2023-02-01 ~ 2025-06-30 |
| valid | 2025-07-01 ~ 2025-12-31 |
| test | 2026-01-01 ~ 2026-09-18 |

## F. 变更清单（均可回滚）

| 文件 | 备份 |
|------|------|
| factor_template/conf_*.yaml ×3 → provider_uri=wb_qlib_data | wb_bak_20260928/ |
| .env +6 行 QLIB_QUANT_* 日期段 | .env.bak_20260928_dataplane |
| experiment/prompts.yaml 注入 wb 字段说明 | prompts.yaml.bak_20260928_wb |
| 新增 wb_qlib_data/、wb_dp_build_fields.py、wb_dp_dump_qlib.py | — |
| ⚠ 官方 cn_data（~/.qlib/qlib_data/cn_data）未动，只改了 provider 指向 | — |
