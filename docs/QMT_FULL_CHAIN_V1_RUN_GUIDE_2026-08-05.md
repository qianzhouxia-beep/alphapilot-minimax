# QMT 全链路实盘模拟策略 v1.0 — 运行与验证指引

日期: 2026-08-05
策略文件: `D:\国金证券QMT交易端\python\qmt_model_full_chain_v1.py`
账户: 8886269286（QMT 实盘模拟）

## 1. 策略是什么

把服务器端 116 维全链路模型的每日评分，在 QMT 上用**真实下单接口**做实盘模拟交易：

- **选股**: 读取 `C:\alphapilot\scores\{YYYYMMDD}.json`，取 Top2（`MAX_HOLDINGS=2`）
- **入场**: GapSoft C（与服务器 `trade_executor.py` 完全一致）
  - 高开 ≤1.5%: 全仓权重 1.0 买入
  - 1.5% ~ 3%: 挂单 `prev*1.01`，权重 0.7
  - 3% ~ 5%: 挂单 `prev*1.02`，权重线性 0.5→0
  - ≥5%: 跳过
- **出场**: 服务器 `trade_executor` 风格自适应
  - 自适应硬止损（按 20 日年化波动率调整，仅 ≥14:45 收盘确认窗口触发）
  - 动态止盈剥皮（浮盈 ≥3% 后回撤 ≥1.5% 减半，最多 2 次；达标后 5% 级剥皮清仓）
  - T+2 强平（≥14:45，亏损时先给 1 天延期，条件 `price ≥ cost*0.95`；盈利直接强平）
  - 跌停保护（当日买入也可卖，`daily ≤ -9.7%`）
- **仓位**: 单只 25% 现金，最多 2 只

## 2. 已完成的验证

| 项目 | 结果 |
|---|---|
| 系统 Python 编译 | PASS |
| QMT 自带 Python 3.6.8 编译（`bin.x64\pythonw.exe`） | `COMPILE_OK` |
| 纯 ASCII / 无 BOM | PASS |
| 零 pandas/numpy 依赖（纯标准库 + 纯 Python 波动率计算） | PASS |
| 端到端 mock（买入→防重→T+1冻结→跌停保护） | 全部 PASS |
| GapSoft C 逻辑 | PASS |
| 自适应参数 / peel 状态机 | PASS |
| 持仓同步防重复买入 | PASS |

## 3. 如何在 QMT 中启动

1. 打开 QMT 交易端，登录账号 **8886269286**
2. 进入"模型研究"或策略编辑器
3. 文件已部署到 `D:\国金证券QMT交易端\python\qmt_model_full_chain_v1.py`
4. **用 QMT 的 Python 模型加载该文件**（文件浏览器选择该 .py，或直接拖入）
5. 选择 **实盘模拟**（不要选回测模式）
6. 运行策略

### 关键注意事项

- **必须运行在实盘/模拟交易模式**。策略里 `do_back_test` 为 False 时才会真正下单。QMT 回测模式下 `handlebar` 不会按真实时间调用，且 `get_trade_detail_data` 不可用。
- **`set_universe` 必须在实盘模式下调用**，否则 `handlebar` 根本不会被触发（这是之前 `主力行为MLV2` 一运行就停的根本原因）。本策略已在 `init()` 和 `handlebar()` 中设置 universe。
- 策略每 **5 分钟**从真实账户同步一次持仓（`_sync_holdings`），重启策略后不会重复买入。
- 分数文件 `C:\alphapilot\scores\{YYYYMMDD}.json` **不会自动同步**（服务器无 cron push）。**每天早上开盘前需手动把最新分数文件放到该目录**，否则当天无信号。

## 4. 运行后如何验证

策略会在 QMT 输出日志中打印：

- `[INIT] full-chain v1.0 | acct=8886269286 | holdings=... | score_dir=...` — 初始化成功
- `[SCORES] 20260805 n=...` — 当日分数加载成功
- `[SYNC] +600519.SH ...` — 持仓同步
- `[BUY] 600519.SH x2500 @ 10.00 w=1.0 open_ok` — 买入
- `[WAIT] ... mid_wait` / `[SKIP] ... gap_ge_5pct` — 入场决策
- `[SELL] ... limit_down ...` / `[PEEL] ...` / `[SELL] ... t2_force ...` — 出场

同时所有成交记录写入 `C:\alphapilot\sim_trades_fullchain.json`（追加式 ledger）。

### 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 无任何 `[SCORES]` 日志 | 分数文件缺失 | 检查 `C:\alphapilot\scores\{当日}.json` 是否存在 |
| 启动即停止 | 未设 universe 或非实盘模式 | 确认走模型研究加载、选实盘模拟 |
| 只有 `[WAIT]` 从不买 | 高开 1.5%~5% 挂单没成交 | 属正常；价格回落命中 limit 才成交 |
| 重复买入同一只 | 持仓同步失效 | 确认 `get_trade_detail_data` 可用（实盘模式） |
| 下单报错 | 账号/资金不足 | 检查账户可用资金、股票权限 |

## 5. 策略源码位置

- 本地源: `C:\Users\elvisq\Projects\alphapilot\qmt_model_full_chain_v1.py`
- QMT 部署: `D:\国金证券QMT交易端\python\qmt_model_full_chain_v1.py`

如需修改参数（如 `MAX_HOLDINGS`、`GAP_OPEN_OK`、`DEF_HARD_STOP`），改源文件后重新复制到 QMT 目录即可（保持纯 ASCII）。
