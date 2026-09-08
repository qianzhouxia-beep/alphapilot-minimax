# QMT 策略「第34行语法错误」最终诊断（2026-08-04 22:50）

- **报错**：`ALPHAPILOT_ML_回测.py_SH00030026 SyntaxError: invalid syntax (<string>, line 34)`
- **时间**：2026-08-04 22:39:53

## 一、本次取证结果

### 1. QMT 里三个策略文件的真实状态（`D:\国金证券QMT交易端\python\`）

| 文件 | 大小 | 磁盘内容 | 实测结果 |
|------|------|---------|---------|
| `ALPHAPILOT_ML_回测.py` | 8,206 B | **加密**（`MiFB...`） | ❌ 今天 22:39 报第 34 行语法错误 |
| `主力行为MLV2.py` | 12,248 B | **明文** 完整版 | ✅ **11:48 回测成功**（见下） |
| `主力行为MLV3.py` | 13,067 B | **明文** 完整 v3.1（本次部署） | ✅ 语法 OK / init+handlebar 齐全 / 纯 ASCII |

### 2. 决定性证据：`主力行为MLV2.py`（明文）在 11:48 回测完整成功

QMT 日志 `XtClient_FormulaOutput_20260804.log`：

```
11:48:18 [TEST] init() called          ← init 被调用
11:48:18 start back test mode
11:48:18 [INIT] model loaded ok
11:48:18 [INIT] feats:33 trees:600     ← 模型加载成功
11:48:18 [INIT] ready
11:48:19 [HB] date=20250728 time=1105 barpos=0
11:48:19 [HB] top2:['300588.SZ']
11:48:19 [DATA] 300588.SZ using 5m bars=13
11:48:19 [MF] 20250728 1105 300588.SZ 0.29/0.31/0.4 -> [HOLD]   ← 信号正常
... （11862 根 5m K 线全部跑完）
11:51:38 calc backtest index           ← 回测完成
```

**结论：明文策略文件放在 `python\` 目录能被 QMT 直接回测/运行，只要代码本身语法正确。**

### 3. `ALPHAPILOT_ML_回测.py` 的问题

- 该文件**不是**本项目提供的任何代码（本地无对应源码）。
- 它是 QMT **加密存储**的策略，创建时间 = 报错时间（22:39:53），即**用户刚保存/运行**。
- QMT 日志显示：`subscribeFormulas ... stockCode:000300, period:86400000`（日线订阅成功）→ `PythonFormula construct` → `Get ALPHAPILOT_ML_回测 from globals failed` → `run script failed! SyntaxError: invalid syntax (<string>, line 34)`。
- **即：启动链路是通的（这次确实挂载了行情），但策略源码第 34 行存在语法错误**——这是代码本身的问题，不是启动方式问题。

## 二、为什么会出现「第34行语法错误」

QMT 加密落盘前会先 `parse`（编译）源码，语法错误在此阶段被拦截。`<string>` 表示 QMT 把源码当字符串解析。

可能原因：
1. **粘贴时代码不完整/被截断**（之前 `主力行为MLV3.py` 就因粘贴不全只剩 157 行、报 `unexpected EOF while parsing (<string>, line 157)`）。
2. **编辑器把长行/特殊字符转换坏**（如全角引号、`→` 等非 ASCII 字符混入字符串字面量外的位置）。
3. 用户从别处复制的回测代码本身第 34 行就写错了。

## 三、正确操作（推荐）

**不要再用 `ALPHAPILOT_ML_回测.py`。直接用已部署好的 `主力行为MLV3`（v3.1 完整版）。**

1. QMT → **模型交易**（或 策略交易）→ 找到 **`主力行为MLV3`**。
2. 打开确认代码是 v3.1 完整版（352 行，纯 ASCII，无空行 docstring）。
3. 选周期：建议先 **5 分钟**（与 11:48 成功回测一致）或 **日线**。
4. 点 **回测** 或 **运行**，观察底部输出应有 `[INIT] model loaded ok` / `[HB]` 信号。

如果一定要用 `ALPHAPILOT_ML_回测` 这个名字：
- 在 QMT 编辑器里**清空该策略代码**，粘贴 v3.1 完整代码（`C:\Users\elvisq\Projects\alphapilot\qmt_model_02_主力行为ML_v3.py`），保存后再运行。

## 四、验证清单（v3.1）

- ✅ 语法：`py_compile` 通过
- ✅ 含 `init(ContextInfo)` 和 `handlebar(ContextInfo)`
- ✅ 纯 ASCII（0 个非 ASCII 字符）
- ✅ 第一行 `#coding:gbk`
- ✅ 352 行 / 13,067 B，完整无截断
