# Cursor → WorkBuddy：视觉桥接（看图）功能已为你安装

> 桥梁人: 钱多爸
> 日期: 2026-08-03
> 用途: 告知 WorkBuddy，已把「看图」能力（Vision Bridge）安装到你的 skills 目录，请审阅对齐。所有资源为本机共享，无需重复下载。

---

## 一、一句话结论

**你（WorkBuddy）现在已经具备看图能力了。** 当用户贴图/截图/发来报错图或图表时，按本技能调用本地 Ollama 视觉模型，把图片转成文字描述/OCR，再基于文字作答。

---

## 二、已安装的位置（自动生效）

技能已复制到你的 skills 目录：

```
C:\Users\elvisq\.workbuddy\skills\vision-bridge\
├── SKILL.md                        # 技能说明（含触发条件与用法）
└── scripts\
    ├── look.py                     # 核心：调本地 Ollama VLM 看图
    └── clipboard_capture.py        # 剪贴板截图落盘（用户刚截的图）
```

**无需任何额外配置**。本机基础设施已就绪：

| 组件 | 位置 | 状态 |
|---|---|---|
| Ollama 服务 | `D:\Ollama\ollama.exe` | ✅ 运行中，开机自启 |
| 视觉模型 | `qwen2.5vl:3b`（3.2GB） | ✅ 已拉取到 `D:\OllamaModels` |
| 测试图片 | `D:\vision_test.png` | ✅ 用于验证 |

> ⚠️ 注意：技能目录由 WorkBuddy 应用扫描加载。若当前会话未自动发现，重启 WorkBuddy 应用即可。

---

## 三、使用方式

触发条件：
- 用户粘贴/提到任何图片（截图、报错弹窗、UI 界面、图表、设计稿、票据文档），期待理解或分析
- 用户说「看图」「识别」「OCR」「这张图里是什么」「describe the screenshot」等

调用方法（模式按场景选）：

```powershell
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image "<图片路径>" --mode general
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image "<图片路径>" --mode ocr
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image "<图片路径>" --mode ui
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image "<图片路径>" --mode diagram
```

| 模式 | 用途 |
|---|---|
| `general` | 通用描述：主体、场景、布局、文字、细节 |
| `ocr` | 逐字提取图中所有可见文字，保留排版顺序 |
| `ui` | 界面截图：页面类型、布局、组件、按钮/菜单文字、异常 |
| `diagram` | 图表/示意图：类型、坐标、趋势、关键数值、结论 |

剪贴板截图（用户刚截的图）：

```powershell
$p = python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\clipboard_capture.py"
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image $p --mode general
```

针对图片特定问题：

```powershell
python "C:\Users\elvisq\.workbuddy\skills\vision-bridge\scripts\look.py" --image "<路径>" --prompt "这个报错窗口里的错误码是多少？请完整读出来"
```

---

## 四、原理

```
用户贴图/报错截图/UI图/图表
      ↓
look.py 调用本地 Ollama VLM（qwen2.5vl:3b）
      ↓
返回详细文字描述 + OCR
      ↓
WorkBuddy 基于文字继续推理、作答
```

本机（Windows）CPU 推理，图片较大时一次约 20~60 秒，属正常现象。

---

## 五、故障排查

- `Ollama 服务未启动`：打开 `D:\Ollama\ollama.exe`（桌面应用）或运行 `ollama serve`
- `model not found`：运行 `ollama pull qwen2.5vl:3b`
- 换模型：`--model minicpm-v`（更强但更慢，CPU 不推荐）
- 换服务地址：`--host http://127.0.0.1:11434` 或环境变量 `OLLAMA_HOST`

---

## 六、与 Cursor 的关系

- 同一套 Ollama + `qwen2.5vl:3b` 模型，**本机共享**，无重复下载。
- Cursor 侧同名技能在 `C:\Users\elvisq\.cursor\skills\vision-bridge\`，脚本逻辑一致，仅目录不同。
- 若后续更换模型/修改脚本，两边同步即可（Cursor 会在此文档更新）。

---

## 状态

- [x] 技能已安装到 `.workbuddy\skills\vision-bridge\`
- [x] 脚本实测通过（OCR 测试：`D:\vision_test.png` → 正确识别）
- [ ] WorkBuddy 确认收到本变更通报
