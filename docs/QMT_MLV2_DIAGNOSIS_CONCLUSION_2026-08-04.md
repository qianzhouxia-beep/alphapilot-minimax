# 主力行为MLV2「运行即停止」诊断结论（磁盘取证版）

- **桥梁人**：WorkBuddy
- **日期**：2026-08-04 19:30
- **上一版**：`QMT_MLV2_STOPS_IMMEDIATELY_2026-08-04.md`（现象 + WorkBuddy 排查）
- **本次产出**：直接读取用户本机 QMT 安装目录 + 运行日志，给出**最终根因**和**可执行操作步骤**

---

## 一、本次取证内容（用户本机 D 盘 QMT 安装目录）

### 1. QMT 安装位置
- `D:\国金证券QMT交易端\`（文档里写的 `b:\` 是旧盘符，实际在 D 盘）
- 内嵌 Python 解释器：`bin.x64\python36.zip`（1.4MB，2022-08-10）——**确认包含 datetime/json/os/time/math/traceback 等全部标准库**，`WorkBuddy 的「datetime 缺失」假设不成立**
- 另有一个 `Python36x64_2025-08-04.zip`（263MB，2026-07-29）——完整版 Python 3.6 环境，**QMT 未用**

### 2. 策略文件对比（`D:\国金证券QMT交易端\python\`）

| 文件 | 大小 | 磁盘内容 | 运行状态 |
|------|------|---------|---------|
| `ALPHAPILOT止盈止损.py` | 31546 B | **加密**（base64 密文） | ✅ 正常 |
| `ML选股回测V206.py` | 14578 B | **加密** | ✅ 正常 |
| `主力行为MLV2.py` | 1992 B | **明文**（`# coding:utf-8`…） | ❌ 只 parse，从不运行 |

**核心发现：所有能正常运行的策略，磁盘上是「加密」的；而用户新建/粘贴的 `主力行为MLV2.py` 是「明文」的。**

### 3. 诊断脚本日志（`C:\alphapilot\qmt_debug.log`）

```
2026-08-04 19:14:01 FILE_LOADED v1     ← 参数名 C
2026-08-04 19:24:50 FILE_LOADED v2     ← 参数名 ContextInfo
2026-08-04 19:25:00 FILE_LOADED v2
2026-08-04 19:25:04 FILE_LOADED v2     ← 连跑 3 次
```

- 每次都是**只有 `FILE_LOADED`，没有 `INIT_START`**
- 参数名从 `C` 改成 `ContextInfo`（与正常策略一致）**依然不触发 init** → **与回调参数名无关**

### 4. QMT 运行日志（`userdata\log\XtClient_Formula_20260804.log`）——决定性证据

**正常策略（ALPHAPILOT止盈止损 / ML选股V206）** 完整运行链：
```
PythonCacheData::subscribeData subscribe, meta:SH_000300_3001_86400000 ...  ← 订阅行情
PythonFormula::continueRun reqid:..._0003007 ... isMain:false
python run from 0 to 33499: ...ALPHAPILOT止盈止损.py_0003007
begin to runonce, bar: 0
[INIT] strategy started | acct=8886269286                              ← init 被调用
```

**主力行为MLV2**（19:13~19:25 全部记录）：
```
19:13:59 [parser]receive save index, name = 主力行为MLV2
19:13:59 [parser]parse complete, name = 主力行为MLV2
19:13:59 [parser]save complete, name = 主力行为MLV2
（19:14:00 / 19:23:49 / 19:24:49 / 19:25:00 / 19:25:03 重复同样的 save/parse）
```

**没有一次 `subscribeData`、没有 `continueRun`、没有 `runonce`、没有 `init`。**

---

## 二、最终根因

**不是 Python 代码问题，也不是周期设置问题，而是「策略从未被 QMT 正式启动运行」。**

1. `FILE_LOADED` 只是 QMT 在 **parse（解析+加载）阶段** 执行了模块顶层代码（`import os, sys...`），不是"运行策略"。
2. 正常策略被 `continueRun`/`runonce` 驱动，逐 bar 调用 `init(ContextInfo)` + `handlebar(ContextInfo)`——**前提是 QMT 已通过 `subscribeData` 把策略挂到了行情数据流上**（周期如 1 分钟 `60000`ms / 日线 `86400000`ms）。
3. `主力行为MLV2` 从未触发数据订阅 → 没有 bar 流 → `init` 永远不会被调用 → 你看到的"开始运行→结束运行"其实就是 **parse/save 完成**，策略根本没跑。

**为什么周期（5分钟/1分钟）无关**：周期只影响 handlebar 触发频率。正常策略用 1 分钟（60000ms）和日线（86400000ms）都能跑；你的策略**压根没被挂载到任何周期上**，所以设几秒都不重要。

**为什么是明文 vs 加密**：QMT 通过「模型交易 / 策略交易」界面正式创建的策略会**加密落盘**；直接在编辑器里粘贴保存的文件是**明文**。明文文件能被 QMT 识别加载（parse），但不会被当作"已启动运行的模型"处理。

---

## 三、对照「QMT 常见问题视频」逐条说明（用户分享 2026-08-04 19:41）

用户分享了 QMT 教学视频，其中 3 条常见回测问题——**逐条对照后均不构成本次根因**：

| 视频经验 | 对本次案例的结论 |
|---------|-----------------|
| ① 代码含中文报错 → 第一行加 `# coding:gbk` | **不是根因**。本机文件实测：正常运行的 `qmt_model_01_ml选股.py` 用 `# coding:gbk`（纯 ASCII），`qmt_stop_loss_tp_v1.5.3.py` 用 `# coding:utf-8`（纯 ASCII）；问题策略 `qmt_model_02_主力行为ML.py` 仅注释含 `→` 等 2 个特殊字符、print 全 ASCII。诊断日志 `FILE_LOADED` 证明**模块能成功加载**，编码未阻塞。且 QMT 正式策略加密落盘，加密后不受源文件编码声明影响 |
| ② `get_market_data_ex` 返回字典（键=代码，值=DataFrame），写法不对拿不到历史行情 | **是回测"取数失败"的常见原因，但非本次实盘根因**。本策略连 init 都没被调用，`get_market_data_ex` 根本没执行到。WorkBuddy 后续写回测逻辑时需注意：`data = get_market_data_ex(...)` 返回 `{code: DataFrame}`，必须 `df = data[code]` 再取列 |
| ③ 回测结束资金不变 → `passorder` 未触发/缺资金账号参数 | **完全不适用**。本策略是**纯信号策略，无 `passorder`**（交接文档已注明"不交易"），不存在下单函数触发问题。视频中提到的 `passorder` 缺少的 `accountID` 参数，仅对真正下单的策略相关 |

**结论**：视频 3 条经验都聚焦"回测代码写错"，而本次是**实盘启动链路未建立**（更前置），两者不重叠。

---

## 四、正确操作步骤（在 QMT 里操作）

1. **不要用普通 Python 编辑器「新建→粘贴→点运行」**。
2. 正确路径：QMT 菜单 → **「模型交易」（或「策略交易」/「条件单」区）** → **新建模型** → 粘贴代码 → 保存。
   - 保存后 QMT 会自动**加密**落盘（对比现有正常策略）。
3. 在「模型交易」列表里选中该模型 → 点 **「启动/运行」** → 选择**运行周期**（建议先用**日线**，跑通后再切 1 分钟/5 分钟）→ 确认启动。
4. 启动后观察 QMT 底部或「模型交易」面板：
   - 正常会看到类似 `[INIT] strategy started` 的输出；
   - 若还是立即"结束"，把 QMT「模型交易」面板的完整提示截图发给 Cursor/WorkBuddy。

---

## 五、给 WorkBuddy 的结论

| 项 | 结论 |
|----|------|
| datetime 缺失 | ❌ 不成立，python36.zip 含全部标准库 |
| 回调参数名 | ❌ 已排除，v2（ContextInfo）仍不触发 |
| set_universe | 需要，但**不是**本次根因（策略根本没启动，谈不上 init 内订阅） |
| 周期 5 分钟/1 分钟 | 无关，周期只影响 handlebar 频率 |
| **真正根因** | **策略未通过「模型交易」正式启动，只有 parse/save，无数据订阅 → init 永不调用** |
| 代码本身 | `FILE_LOADED` 证明模块可加载，语法/编码无问题 |

**建议**：QMT 端由用户按「第三部分」操作把策略在「模型交易」里正式启动。若用户坚持用编辑器方式，则 QMT 无法满足——需要把信号计算移到服务器（`scores/{YYYYMMDD}.json` 已每天生成，QMT 只读即可）。
