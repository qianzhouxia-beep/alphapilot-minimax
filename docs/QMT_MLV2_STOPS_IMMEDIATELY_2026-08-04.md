# 问题交接：主力行为MLV2 在 QMT 点"运行"立即停止（求助 Cursor）

- **桥梁人**：WorkBuddy
- **日期**：2026-08-04 14:20
- **用途**：将 QMT 端「主力行为MLV2」策略"运行即停止"问题完整交接给 Cursor，请协助定位根因
- **重要**：WorkBuddy 负责服务器/数据侧，QMT 端（用户本机）代码归 Cursor 维护

---

## 一、现象

**策略文件**：`qmt_model_02_主力行为ML.py`（QMT 内嵌 Python 编辑器，用户粘贴运行）

| 模式 | 结果 |
|------|------|
| **回测**（点"回测"按钮）| ✅ 正常，输出 `[HB]` / `[DATA]` / `[MF]` 完整信号（sell/hold/buy 概率）|
| **实盘**（点"运行"按钮）| ❌ **立即停止**：QMT 底部只显示 `[主力行为MLV2]开始运行` → `[主力行为MLV2]结束运行`，无任何 `[INIT]` / `[HB]` 输出 |

**已确认**：
- 策略编辑器「编译」**成功**（14:06:29 与 14:13:09 两次"编译成功"，说明语法 OK）
- 用户**粘贴的是最新版代码**（含 SIGNAL_LOG / set_universe / timetag 兜底）
- 同机 **ALPHAPILOT止盈止损** 策略（实盘）正常运行——**对照组**：其 `init()` 里有 `ContextInfo.set_universe(持仓列表)` 订阅行情
- QMT 使用**内嵌 Python 3.6 zip 解释器**（traceback 路径：`b:\国金证券QMT交易端\bin.x64\python36.zip\json\encoder.py`）

---

## 二、WorkBuddy 已做的排查与修改（最新版代码含以下改动）

1. **加 set_universe 订阅**（init 第 4 步）：`C.set_universe(['600519.SH'])` —— QMT 实盘必须订阅 ≥1 标的才会喂 handlebar，否则立即停（回测用本地 K 线不受限）。对照 ALPHAPILOT 证实该推断。
2. **timetag_to_datetime 兜底**：顶部 try-probe，若 QMT 无内置则用 `time.strftime(time.localtime(ts))` 自实现。
3. **去掉 `from datetime import datetime` 依赖**（最新版）→ 全用 `import time` 标准库。**怀疑 QMT zip 内嵌 Python 缺 datetime 模块 → ImportError → 策略加载失败**。
4. **init 简化为 7 行**（只 set_universe + print），模型加载移到 `_ensure_model()` lazy-load（handlebar 首次调用时加载）—— init 0 外部依赖。

**最新版代码文件**：`C:\Users\elvisq\Projects\alphapilot\qmt_model_02_主力行为ML.py`（本地 + 服务器 `/home/ubuntu/alphapilot/` 均有一份）

---

## 三、求助 Cursor 的核心问题

1. **QMT「运行即停止」最可能的根因**是什么？（已排除：编译错误 / 缓存 / set_universe 缺失 / datetime 依赖——如果最新版仍失败）
   - QMT 内嵌 Python 3.6 zip 环境**缺少哪些标准库**？（datetime? 还是其他）
   - 如何**看到真实的 init/handlebar 异常**？（QMT 的"编译输出"与"日志输出"两个标签分别显示什么；策略运行时的 Python 异常/print 到底输出到哪）
2. **set_universe 正确用法**：实盘模式下是否需要 `set_universe` + 周期订阅？`C.set_universe(['600519.SH'])` 的参数格式对吗（`600519.SH` vs `SH600519`）？
3. **为什么回测能跑、实盘不能跑**——除 set_universe 外还有什么差异（行情连接、账号权限、数据源）？
4. 若 zip 内嵌 Python 缺模块，**最优替代方案**：是否应把 XGBoost 树推理逻辑移出 QMT（改由服务器每天算好信号写 JSON，QMT 只读）？

---

## 四、补充信息（供 Cursor 判断）

- 策略逻辑：读 `C:\alphapilot\scores\{YYYYMMDD}.json`（每日 09:50 同步）Top2 → `get_market_data_ex` 拉 5m/1d K 线 → 33 特征 → 600 棵 XGBoost 树（`C:\alphapilot\models\main_force_v2_trees.json`）→ 输出 sell/hold/buy 概率 + 信号
- **纯信号策略，不交易**（无 passorder）
- 数据依赖：scores（WorkBuddy 每日同步）+ 模型文件（18MB JSON）
- 用户可操作项：QMT 编辑器粘贴代码 → 编译 → 运行；日志在编辑器底部「编译输出 / 日志输出」两个标签

---

## 五、期望产出

- Cursor 判断根因 + 给出**能在 QMT 实盘稳定运行**的最终代码（或明确"QMT 端不适合跑该模型，改服务器算信号"的结论）
- 若 QMT 无法显示运行时异常，提供替代调试手段（如写日志到文件）
