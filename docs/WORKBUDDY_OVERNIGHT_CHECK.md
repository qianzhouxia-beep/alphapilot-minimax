# WorkBuddy：外盘 / 隔夜每日巡检指令

把下面整段发给 WorkBuddy，作为**每个交易日固定职责**（建议时间：凌晨 05:15～05:30，管线 05:00 跑完后；盘前再抽查一次 08:40）。

---

## 角色

你负责 AlphaPilot 上海机（`ubuntu@150.158.100.236`，目录 `/home/ubuntu/alphapilot`）的**外盘隔夜数据巡检与补救**。  
不要改选股/交易核心代码；只跑巡检脚本、补拉数据、把结果回我。

## 为什么外盘重要

- **美股晚间板块走势权重大于「昨日 A 股收盘研报」**。例如美股半导体大涨，次日相关 A 股应有映射加分优势。
- 昨日收盘研报描述的是 **1/2/3/5 日已发生资金结构**，用来判断板块趋势梯队（prefer/avoid），**不能当成「明天就会同样流入」**。
- 05:00 管线依赖：`us_enhanced_collector.py` + `overnight_sentiment.py`（写出 `output/overnight_sentiment.json` / `overnight_signals.json`）。

## 每日检查（必做）

```bash
cd /home/ubuntu/alphapilot
python3 -u scripts/check_overnight_freshness.py
```

### 通过标准（全部满足才算 OK）

1. 命令打印 `OVERNIGHT_OK`
2. `output/overnight_sentiment.json`、`output/overnight_signals.json` **存在**
3. 文件 `fetched_at` / mtime 是**今天凌晨**（或昨晚 20:00 之后）
4. `us_symbol_count` ≥ 5，或 `sector_bonus` 非空
5. `output/us_enhanced_factors.json` 的 `fetched_at` 也尽量是今天（可与隔夜一并看）

### 失败时补救

```bash
cd /home/ubuntu/alphapilot
python3 -u scripts/check_overnight_freshness.py --repair
```

仍失败则：

1. 把终端完整输出贴给我
2. 另存：`output/overnight_alerts.json`（脚本会写）
3. 不要擅自改 `recommend.py` / `trade_executor.py`

## 可选：盘前 08:40 再验一次

```bash
cd /home/ubuntu/alphapilot
python3 -u scripts/check_overnight_freshness.py --max-age-hours=14
ls -la output/overnight_sentiment.json output/overnight_signals.json output/us_enhanced_factors.json
```

## 回我时的固定格式

```
【外盘巡检】日期：YYYY-MM-DD
结果：OK / FAIL
overnight_sentiment fetched_at：...
us_enhanced fetched_at：...
us_symbol_count / sector_bonus 数：...
是否执行 --repair：是/否
repair 后：OK / 仍 FAIL（附日志）
```

## 不要做的事

- 不要 git checkout 管线核心文件
- 不要为了「看起来成功」伪造 JSON
- 隔夜失败时，早盘选股仍可能跑，但必须明确告警「外盘未新鲜」
