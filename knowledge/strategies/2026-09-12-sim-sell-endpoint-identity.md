# 交易端模拟盘「卖出端文件身份」核查（2026-09-12）

> 状态：**已核实（同机 HEAD `4c2b8dd`）** ｜ 层：买卖模型 ｜ 触发：老板拍板「以 Track A 模拟盘卖出端为基准，让 Track B 模拟盘对齐」，WB-Mac 开工前要求先核对基准身份。
> 权威文件：`production_strategies/track_a/TrackA_track_a_qmt_full_chain_sim_v2.45.py`（A sim）、`production_strategies/track_b/TrackB_track_b_qmt_auction_sim_v2.13.py`（B sim）。

## 一、结论速览

| 问题 | 结论 |
|---|---|
| 参与 A/B 两个 QMT 模拟盘**卖出决策**的文件 | **只有这两份 sim 本身**（完全自包含，`import` 仅 stdlib `os/json/time/math/datetime`） |
| 是否存在第三个活动文件 | **无**。TDX 端用**另一套账户**（`1190388433`），server 侧不下 QMT 单，`adaptive_exit.py` 只存在于文档 |
| ⚠️ 真实风险 | **旧备份自带可用账户号**：`track_b/…sim_v2.12.py` 的 `ACCOUNT_ID=98009473`（**A 的账户**）、`track_a/…sim_v2.27.py`（`98009473`）。**若被 QMT 加载会污染 A 账户 / 双策略重复决策** |
| `_check_sell` 范围 | A **2647–2933**（下一顶层 def `_hold_days` @2934）；B **2276–2428**（@2429） |
| `server/adaptive_exit.py` | **不参与**（2026-08-06 盘中买卖点研究原型，仅 docs/knowledge 引用，零 `.py` 命中） |

## 二、账户隔离（谁能对哪个账户下单）

| 账户 | 用途 | 仓库内出现的文件 |
|---|---|---|
| `98009473` | **A 模拟** | `track_a/…sim_v2.45.py` L390；`track_a/…sim_v2.27.py`（旧备份）L255 |
| `62128716` | **B 模拟** | `track_b/…sim_v2.13.py` L237；`_probe_qmt_order_fields.py`（**只读**，只 query 不下单） |
| `8886269286` | **实盘** | 两个 live 模板 |
| `1190388433` | **TDX 量化 sim** | 两个 TDX 文件（无 `passorder`，走 `tq.*`） |

⇒ **账户号一致的文件才能向该账户下单**。因此"第三个文件"的唯一现实来源是**误把旧备份留在 QMT 策略目录里**（QMT 加载目录里有什么，不看仓库部署表）。

## 三、A 独有 / B 缺失的卖出机制（对齐工单输入）

A 有、B 无（常量位置为 A 侧）：

| # | 机制 | A 常量 / 位置 |
|---|---|---|
| M1 | SHADOW-B3 只读记录（首次 −2% 触碰，零订单影响） | `SHADOW_B3_STOP_PCT=2.0` @L3136；触价 @L2689 |
| M2 | **−4% 全天候盘中止损**（T+1 起，不限 14:45）+ D8 豁免 + 灾害地板 | `FIXED_STOP_PCT=4.0` @L634；`if ret <= -FIXED_STOP_PCT` @L2694 |
| M3 | **TSDOWN**：TrendState 新翻 DOWN → 次日开盘半卖 | `TSDOWN_ENABLE=True` @L654；@L2726 |
| M4 | **weak_regime 动态**：地板 ×0.6 / T+3 改「跌破 MA25 才卖」/ 延期需站上 MA25（含 `_weak_cap_sell_ok` @L2805） | `WEAK_REGIME_ENABLE=True` @L545、`WEAK_FLOOR_MULT=0.6` @L546、`WEAK_TREND_MA=25` @L547 |
| M5 | **peel：上限 2% + 下一根 5m bar 确认** ⭐版本相关 | `PEEL_PB_MAX=0.02` @L529、`PEEL_NEXT_BAR_CONFIRM=True` @L537；生效行 `_adaptive_params`(@2066) 内 L2074 |
| M6 | **D8 观察名单**（深亏票豁免机械卖出，只留 −8% 地板 + 三条件释放） | `OBSERVE_FILE` @L647、`D8REL_SCORE_MIN=55.0`@L659、`D8REL_DAYS=2`@L660、`D8REL_T3=1.0`@L661 |
| M7 | **纪律止损 → 5 交易日买入冷却** | `COOLDOWN_STOP_DAYS=5` @L637、`STOP_TOKENS` @L914；`_mark_cooldown` @L3290 |
| M8 | `_do_sell` 健壮性：可卖量夹取 / 拒单不动持仓 | `def _do_sell` @L3247；拒单 `return` @L3282-3285 |
| M9 | **`ROTATION_ENABLE` 反向**：A=`False`（@L576，v2.29 起关）、B=`True`（@L425） | **方向待定** |

**两侧逐字节相同**（10 常量 + 5 函数，已核）：`DEF_HARD_STOP=-0.10`、`DEF_TRAIL_ARM=0.03`、`DEF_PEEL_PB=0.015`、`PEEL_MAX_STEPS=2`、`T2_FORCE_HHMM=14*60+45`、`T2_EXTEND_MAX_DAYS=3`、`ANOMALY_PCT=-21.0`、`LIMIT_DOWN_PCT=-9.7`、`VWAP_SELL_START=9*60+35`、`VWAP_SELL_END=9*60+50`；`_vwap_clear_early`/`_t2_force_floor`/`_vwap_morning_decide`/`_hold_days`/`_wyckoff_*`。

## 四、⚠️ 待定：现场 A 模拟盘实际版本（决定"基准"是否成立）

**Mac 无法定案**，证据两侧：

- **倾向非 v2.45**：`checkpoints` 09-10 三条（v2.43/44/45）状态均为「待老板部署模拟盘」，无一条改"已部署"；09-11 审计 Track A QMT 拉取 09-10 **0 次**、09-11 仅 3 次（**策略未运行**）。
- **倾向 v2.45**：老板 09-12 称「Windows 端与最新代码对齐」；09-12 11:21 有策略重启日志。

**关键**：M1–M8 中**只有 M5（peel 2% + 次 bar）是 v2.44/45 新增的卖出机制**。若现场是 v2.42，其 peel = **上限 5% + 首触即卖** ⇒ **照仓库 v2.45 定基准会把"现场并没在跑"的规则当基准**。

⇒ 处置：基准暂定义「仓库 `A sim v2.45` 卖出端」但**不冻结**；**M5 单列为待定项**；先由 `r4gOT8` 现场采 `[INIT]` 原文 + 目录全部 `.py` 的 md5。

## 五、待办（建议）

1. **把旧备份移出可部署目录**（或加 `_backup` 后缀 + 注释）：`track_b/…sim_v2.12.py`、`track_a/…sim_v2.27.py`——它们自带账户号，误加载即污染。
2. `r4gOT8` 现场采集：策略目录**全部** `.py` 名+大小+时间+md5（不预设文件名）+ `[INIT]` 原文。
3. 对齐工单：M5 待定、M9 方向待拍板，其余 M1–M4/M6–M8 可直接列为 A→B 搬运项。

## 关联

- `production_strategies/README.md` §四 部署基线（md5/行尾/`[INIT]`）
- `knowledge/strategies/buy_sell_rules.md`（各机制上线依据）
- Issue #6 comment `5645882552`（WB-Mac 提问）与本次回复
