# 港股/美股纸盘框架 v1（HK/US Paper Framework）

> 作者 Cursor 2026-09-10。数据/运行归属：**新加坡服务器 `/home/ubuntu/alphapilot/hk/`**。
> 与 A 股生产完全隔离；研究/纸盘先跑，实盘后议。

## 设计原则
- **市场无关接口**：HK 先行，US 同接口（`sources.fetch_us_kline` / `COST["US"]`）。
- **透明基线**：打分 = 因子横截面 z-score × 方向 × 权重（不先上 ML）。
- **L1-L6 数据纪律**：原子写、readiness 闸、单入口、失败留痕。
- **不偷看未来**：南向持股 T+1 披露滞后内置（`Context.south_asof` 取严格早于打分日的截面）。

## 目录 / 模块
```
config.py        配置：路径/成本/权重/池阈/持仓参数
dataio.py        UA-aware HTTP、原子 JSON 读写、交易日历
sources.py       抓取 K线(HK/US)、南向持股截面(WAF安全 filter)、建池
factors.py       因子注册表 + 价格族(mom/trend/vol/dd) + 南向族
signals.py       透明加权打分 + 闸门
paper.py         交易成本 + 纸盘引擎(事件循环/ledger/equity)
daily_update.py  每日管线：K线→南向→建池→readiness(→picks)
run_paper.py     用现有数据回放一遍纸盘
```

## 数据布局（`HK_BASE/data/`）
```
pool.json               池子(代码 + med_amt + 南向持股)
kline.json              code -> [{d,o,c,h,l,v}, ...]
southbound_hist.json    hold_date -> {code: {r,s,m,chg,amp}}
factor_weights.json     (可选) 覆盖默认权重
```
输出在 `HK_BASE/output/`：`readiness.json` / `picks_{date}.json` /
`paper_state.json` / `paper_ledger.jsonl` / `paper_equity.jsonl`。

## 运行
```bash
export HK_BASE=/home/ubuntu/alphapilot/hk
python3 daily_update.py            # 每日数据管线（盘后）
python3 daily_update.py --picks    # 附带当日打分
python3 run_paper.py               # 纸盘回放
```

## 部署（新加坡 `/home/ubuntu/alphapilot/hk/`）
代码与数据已就位并跑通（2026-09-10 11:34：readiness=ready，池 448）。
日更定时（**待安装**，港股收盘后 + 南向 T+1 披露后各一次）：
```cron
# 港股收盘后拉当日K线
20 17 * * 1-5 cd /home/ubuntu/alphapilot/hk && HK_BASE=/home/ubuntu/alphapilot/hk python3 daily_update.py >> output/daily.log 2>&1
# 次日补南向持股(T+1)后刷新池与选股
10 09 * * 1-5 cd /home/ubuntu/alphapilot/hk && HK_BASE=/home/ubuntu/alphapilot/hk python3 daily_update.py --no-kline --picks >> output/daily.log 2>&1
```
readiness 告警可并入既有巡检（读 `output/readiness.json` 的 `ready` 与 `checks`）。

## 时序（与南向 IC 口径一致）
```
T 收盘算信号 → T+1 开盘买入（滑点）→ 持有 HOLD_DAYS → 到期日收盘卖出（滑点）
费用：HK 印花税 0.1% 双边 + 佣金(最低) + 平台费；US SEC 费(仅卖) + 佣金
```

## 现状 / 待办
- [x] 数据管线（K线 / 南向 / 池 / readiness）
- [x] 价格族 + 南向族因子（南向已实证为反向/风险信号，默认 dir=-1）
- [x] 透明打分 + 闸门
- [x] 纸盘引擎 + 费用模型
- [ ] 定时任务（cron/systemd）+ 告警接入
- [ ] 质量类因子（ROE/负债）— 需基本面数据源
- [ ] 美股池 + 美股因子
- [ ] 券商沙盒接线（富途/老虎/Alpaca）

## 已知坑
- 腾讯行情 cloud IP **必须带 UA + Referer**，否则假性限流。
- 东财 datacenter filter 在**新加坡**需**只 URL 编码引号**（括号/等号原样），否则 400。
- 南向 `MUTUAL_TYPE` 002/004 同构，取一份即可。
- 回测**必须用 `ctx.pool_for(date)`（逐日 point-in-time universe）**，不能用固定池，否则前视/存活偏差。
- 做空**必须过现实约束**（见下），否则 naive 多空会虚高数倍。

## 多空 / 做严（2026-09-10 增，结论见 `knowledge/inbox/2026-09-10-hk-swing-rigor.md`）
模块：
- `paper_ls.py`：带符号持仓的多空引擎（`long_only` / `long_short` / `long_hedge`），含借券费、空头滑点。
- `run_modes.py`：三模式对比（同起点）。
- `_fetch_shortable.py`：抓港交所「可卖空指定证券名单」→ `data/shortable.json`（需每周跑）。
- `_fill_missing.py`：补齐退出港股通的票的K线（消除存活偏差）。

做空现实约束（`config.py`）：名单内 + 非仙股(≥1 HKD) + 排除前日 |涨跌|>25% 妖股 + 借券费 8%/年 + 空头滑点 0.3%。

**核心结论**：
1. 港股**成本是第一约束**——H=5 长多毛利 +5.7% 但净 -2.7%；多空毛利 +14.6% 净 **-29.7%**（印花税+换手）。
2. 慢因子应**拉长持有**：H=15 是多空净收益甜蜜点（样本外 Sharpe 1.86）。
3. **样本外多头持续亏**（只是低 beta）；**利润几乎全在空头**（= 空「高波动+南向拥挤」垃圾股，regime 依赖）。
4. **用途定位：南向拥挤/高波动 = 风险过滤 + 空头信号，不是买入信号。**

