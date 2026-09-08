# QMT 全链路策略 v2.0 — 实时盯盘运行指引

日期: 2026-08-09
策略文件:
- 实盘端: `D:\国金证券QMT交易端\python\qmt_model_full_chain_v2.py`
- 模拟端: `D:\国金QMT交易端模拟\python\qmt_model_full_chain_v2.py`
账户: 98009473（QMT 模拟 / 实盘）

## 1. 策略是什么

把服务器端 116 维全链路模型的每日评分，在 QMT 上用**真实下单接口**做实时模拟/实盘交易：

- **候选池**: 读取 `C:\alphapilot\scores\{YYYYMMDD}.candidates.json`（Top10，先到先得）
- **入场**: P2 动态确认（与服务器 `intraday_low.dyn_confirm_price` 完全一致）
  - ① 趋势确认: 现价 > 09:35 定格价 且 现价 > VWAP
  - ② 量能确认: 近 2 根 5 分钟 K 线至少 1 根 量比>1.3 且 收阳
  - ③ 不追高: 现价 ≤ 昨收 × 1.05
  - 三条件同时满足 → 以触发实时价买入（事件驱动，先到先得）
  - 未触发 → 放弃（不 fallback，宁缺毋滥）
- **出场**: 自适应硬止损 + 动态止盈剥皮 + T+2 强平 + 跌停保护
- **仓位**: 单只 25% 现金，最多 2 只

## 2. 实时盯盘 —— 关键设置（务必核对）

QMT 策略是**事件驱动**：行情每推送一次，`handlebar` 就被调用一次。
**实时性完全由 QMT 触发周期决定**，必须在 QMT 界面设置：

| 设置项 | 必须值 | 效果 |
|---|---|---|
| **运行周期** | **1 分钟** 或 **分笔(tick)** | 1 分钟 → 每分钟判断一次 P2；tick → 每笔成交推送就判断（秒级） |
| 运行模式 | **实盘/模拟交易**（不是回测） | 回测模式不触发真实下单 |
| `set_universe` | 脚本已自动设置（持仓 + Top10 候选） | 不设则 `handlebar` 根本不被触发 |

### 周期与 P2 的配合

P2 的量能确认依赖 5 分钟 K 线（每 5 分钟收盘定型）。因此：
- **触发粒度 = 1 分钟**: 每根 5 分钟 K 收盘后 ≤1 分钟内买入，已经是"放量上攻刚发生就买"。
- **触发粒度 = tick**: 条件成立的瞬间即买（更激进，适合想抓第一波放量）。

两种都能做到"达到量能就马上买入"，**不要用 5 分钟或日线周期**，否则 P2 判断会滞后一整根 K 线。

## 3. 已修复的问题（2026-08-09）

| 问题 | 影响 | 修复 |
|---|---|---|
| P2 参考价传成了模型评分 | `现价 > 09:35 定格价` 恒为真，趋势确认失效 | 改为用 QMT 第一根 5m bar 的 close 作为 09:35 定格价 |
| `no_quote`/`no_m5` 被永久标记放弃 | 某次行情抖动会把候选"当天报废"，漏掉买入 | 仅 `no_confirm_eod`（过 14:57）才永久放弃，其余下周期重试 |

## 4. 如何在 QMT 中启动

1. 打开 QMT 交易端，登录账号 **98009473**（模拟端/实盘端分别登录）
2. 进入"模型研究"或策略编辑器
3. 用 QMT 的 Python 模型加载 `qmt_model_full_chain_v2.py`
4. **运行周期选 1 分钟（或分笔 tick）**，模式选**实盘/模拟交易**
5. 运行策略

### 关键注意事项

- **必须运行在实盘/模拟交易模式**。`do_back_test` 为 False 时才会真正下单。
- **`set_universe` 必须在实盘模式下调用**，否则 `handlebar` 根本不会被触发。
### 分数/候选文件同步（全自动，无需手动）

- Windows 计划任务 `AlphaPilotSyncQmtScores` 已配置，**每天 09:36 自动运行**
  `scripts\sync_qmt_scores.py --poll`，在 09:36–09:45 窗口内每分钟轮询一次，
  服务器一旦生成当天 `output/qmt_scores/{YYYYMMDD}.json` 与
  `{YYYYMMDD}.candidates.json`，自动拉取到本地 `C:\alphapilot\scores\`。
- 无需任何手动操作。若某天没拉到，可手动执行
  `python scripts\sync_qmt_scores.py --once` 补拉。
- 计划任务用 `pythonw`（无窗口），日志在 `C:\alphapilot\scores\_last_sync_result.json`。
- 策略每 5 分钟从真实账户同步一次持仓（`_sync_holdings`），重启策略后不会重复买入。

## 5. 运行后如何验证

策略会在 QMT 输出日志中打印：

- `[INIT] full-chain v2.0 (P2 dyn-confirm) | acct=98009473 ...` — 初始化成功
- `[CAND] 20260809 n=10` — 当日 Top10 候选池加载成功
- `[WAIT] 600519.SH P2=wait_confirm rank=1 retry next period` — 尚未触发，持续轮询
- `[BUY] 600519.SH x2500 @ 10.00 P2=dyn_confirm rank=1` — 放量上攻触发，实时价买入
- `[WAIT] ... P2=no_confirm_eod ... abandon for today` — 过 14:57 未触发，当天放弃
- `[SELL] ... limit_down / t2_force / peel_clear` — 出场

所有成交记录写入 `C:\alphapilot\sim_trades_fullchain.json`（追加式 ledger）。

## 6. 与网页端 Paper Trade 的区别

| | 网页端 Paper Trade | QMT 模拟 / 实盘 |
|---|---|---|
| 运行位置 | 腾讯云服务器 | 本地 Windows QMT 交易端 |
| 数据源 | 腾讯免费接口（10 分钟轮询） | 券商实时行情（订阅推送） |
| 实时粒度 | 每 10 分钟 | 1 分钟 / tick（秒级） |
| 下单 | 模拟记账 | 真实下单（模拟或实盘账户） |

## 7. 策略源码位置

- 本地源: `C:\Users\elvisq\Projects\alphapilot\qmt_model_full_chain_v2.py`
- QMT 部署: 实盘端 `D:\国金证券QMT交易端\python\` / 模拟端 `D:\国金QMT交易端模拟\python\`

如需修改参数（如 `MAX_HOLDINGS`、`CONF_VOL_RATIO`），改源文件后重新复制到 QMT 目录即可（**保持纯 ASCII**）。
