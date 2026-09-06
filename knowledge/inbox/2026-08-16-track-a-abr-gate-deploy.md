# 2026-08-16 Track A ABR 门接入 —— 归档确认

> 状态：文件已整理归档，待用户部署。知识库已更新。

## 本次动作

1. **ABR（主动买占比）门已写入 Track A 三份策略**（`production_strategies/track_a/`）：
   - `TrackA_qmt_model_full_chain_v2.py` v2.12 → **v2.13**（QMT 模拟）
   - `TrackA_qmt_model_full_chain_template.py` v2.12-tpl → **v2.13-tpl**（QMT 实盘模板）
   - `TrackA_tdx_full_chain.py` v2.10 → **v2.11**（TDX 模拟）

2. **实现要点**：
   - P2 触发后，连续竞价时段（≥09:30）检查主动买占比，`< 0.52` → `skip_low_abr`（当日放弃）
   - 数据源：QMT = mootdx_feed 当日累计逐笔 ABR → 回退 L1 逐笔近似；TDX = 盘口买一档量占比
   - **软门**：ABR 不可用不拦截；卖出侧不加 ASR 早退（回测证伪）

3. **回测依据**（扩样本，114 候选 / 20 交易日真实 Top10）：
   - T+1 胜率 42.3% → 54.2%；T+1 均收益 -0.46% → +0.36%（由负转正）
   - 详见 `production_strategies/track_a/BT_ABR_GATE_REPORT.md`

## 归档 & 对齐

- QMT 模拟与实盘模板逻辑逐行一致（仅 CONFIG/路径/注释差异）✅
- `_top10_dates.json`（回测合并计划）已移入 track_a，`fetch_tick_abr.py` 默认路径已同步 ✅
- 三份策略 `py_compile` 语法全过 ✅
- `production_strategies/README.md` / `CHANGELOG.md` 已更新版本号与记录 ✅

## 待用户部署（模拟端/实盘端用户自行部署）

| 文件 | 目标 | 前置 |
|---|---|---|
| `track_a/TrackA_qmt_model_full_chain_v2.py` | QMT 模拟 python 目录（明文） | 启动 `mootdx_feed.py` |
| `track_a/TrackA_qmt_model_full_chain_template.py` | QMT 实盘，每账户一份改 CONFIG | 启动 `mootdx_feed.py` |
| `track_a/TrackA_tdx_full_chain.py` | TDX `PYPlugins\user` | 无（盘口近似） |

> 部署注意：QMT 文件保持纯 ASCII 明文，勿用 QMT 编辑器保存（会 GBK 重编码+加密导致 SyntaxError）。
> `MIN_ACTIVE_BUY=0.52` 保守档；想更严格可改 0.55（T+1 胜率 57.9%）。

## 知识库更新记录

- `knowledge/signals/index.md`：新增「P2 累计主动买占比门（ABR≥0.52）」信号卡
- `knowledge/strategies/buy_sell_rules.md`：买入规则新增 Track A ABR 门一节
- `knowledge/decisions/index.md`：新增 2026-08-16 决策行
- `knowledge/data_sources/index.md`：新增「逐笔成交 / 主动买占比（免费）」数据源一节
