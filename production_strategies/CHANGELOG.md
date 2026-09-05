# 生产策略更新日志（CHANGELOG）

> 所有对 `production_strategies/` 内生产文件的修改，必须在此追加记录。
> **追加在最新一条的上面（倒序）**，不要覆盖旧记录。

## 记录模板（复制后填写）

```
## YYYY-MM-DD
- 修改人/Agent：谁改的（如：主控 Agent / DeepSeek Harness / 其他 Agent）
- 涉及文件：文件名（含 track_a/track_b/server/docs 路径）
- 版本变化：vX.Y → vX.Y+（若改逻辑）或 无（若只改配置/注释）
- 修改内容：改了什么，改了哪几处
- 原因/依据：为什么改（bug 号 / 交叉验证发现 / 需求变更）
- 验证：ASCII / 语法 / 离线测试 结果
- 部署：是否需要重新部署到交易端，部署到哪
```

---

## 2026-09-04 短窄缩 1/2/3：loud_vol 软门 + sns 软降权（A v2.36 / B v2.10）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（T-1：loud_vol / quiet_accum / up_shrink / sns_score；gene 软排序；fullpool stamp）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.35 → v2.36）
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.35-tpl → v2.36-tpl）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.9 → v2.10）
  - `track_b/TrackB_track_b_qmt_auction_sim_v2.6.py`（同上）
- 版本变化：买入资格变化，A 升 v2.36，B sim 升 v2.10
- 修改内容：
  1. **loud_vol**：T-1 涨日且 `volume/MA20 >= 2.5` → 打标；A rank 窗 / B money_pass **硬 skip**（`[LOUD]`）。
  2. **sns**：`quiet_accum`（近5日振幅中位≤3%+阳≥3+量≤MA20）+ `up_shrink`（涨日均量/跌日均量≤0.9）；gene 内 sns 加分，**不加重 lim10**。
  3. gene 排序：path_fade 沉底 → loud_vol 沉底 → gene_score → sns_score。
  4. **明确不做**：红三兵/跳空硬买、加码 lim10（见 inbox 决策卡）。
- 原因/依据：操盘手「真拉升缩量/假拉升锣鼓喧天」。本地 40 日 as-of：loud_vol T+1 **−0.78%**/胜率38%；quiet∩up_shrink **+0.37%**/胜率55%（universe +0.08%/51%）。`output/bt_sns_factors_t1.json`。
- 验证：四份 QMT ASCII+ast；server smoke `_load_t1_path_frame` t1=2026-09-03 OK；已 scp。
- 部署：server **已部署**。**需用户手动复制** QMT A 实盘+模拟 v2.36、B 模拟 v2.10。

## 2026-09-03 path_fade 收紧：取消 lim10≥3 豁免

- 修改人/Agent：主控 Agent
- 涉及文件：`server/export_qmt_scores.py`（`_load_t1_path_frame` path_fade 条件）
- 版本变化：server 规则收紧；QMT A v2.35 / B sim v2.9 **客户端逻辑不变**（仍读 server 的 `path_fade` 字段）
- 修改内容：删除 `limit_cnt_10d < 3` 豁免——**凡**近5日有涨停 + T-1 高开低走收低，一律 `path_fade=True`，连板也不例外。
- 原因/依据：用户认为 lim10≥3 豁免过冒险；弱市下连板次日高开低走同样可能是见顶形态。
- 验证：server ast parse OK。
- 部署：server **需已 scp**；QMT 文件仅注释同步，**不必因本条重部署**（行为由 server 打标决定）。

## 2026-09-03 path_fade：A+B 同步跳过「涨停后高开低走」（v2.35 / v2.9）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（`_load_t1_path_frame` / `_stamp_path_and_lim10` / gene 重排降权 path_fade）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.34 → v2.35）
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.34-tpl → v2.35-tpl）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.8 → v2.9）
  - `track_b/TrackB_track_b_qmt_auction_sim_v2.6.py`（v2.8 → v2.9）
- 版本变化：买入逻辑变化，A 升 v2.35，B sim 升 v2.9
- 修改内容：
  1. **path_fade 定义**（T-1 日线）：近 5 日有涨停 **且** 高开≥1% **且** 阴线 **且** 收盘在振幅下 15%（**无豁免**，2026-09-03 晚取消 lim10≥3 例外）。
  2. **server**：candidates 基因重排时 path_fade 降到池底并打标；fullpool_live 打 `limit_cnt_10d` + `path_fade`。
  3. **轨道 A QMT**：rank 1–3 窗口内 **直接跳过** path_fade（日志 `[PATH]`）。
  4. **轨道 B sim**：money_pass LIM10 候选池 **先踢 path_fade** 再取 lim10 top2（日志 `[PATH]` / `[LIM10]`）。
- 原因/依据：用户判断当前缩量弱市下，多数涨停股 T-1 高开低走后会调整；仅极强连板可例外。全市场 HOLC 次日偏反弹，但 **涨停后再 HOLC** 次日转负（inbox `2026-09-03-holc-marketwide-nextday.md`）；300413 案例。A/B 买卖端规则对齐。
- 验证：四份 QMT 文件 ASCII+ast；server ast parse OK。
- 部署：server **需 scp 覆盖** `/home/ubuntu/alphapilot/export_qmt_scores.py`（明早 cron 自动带 path_fade）。**需用户手动复制** QMT A 实盘+模拟 v2.35、B 模拟 v2.9。

## 2026-09-03 Track B sim v2.8：LIM10（money_pass 内按近10日涨停次数取前2）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（`--fullpool-live` 增加 `_stamp_limit_cnt_10d`）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.7 → v2.8）
  - `track_b/TrackB_track_b_qmt_auction_sim_v2.6.py`（同上；用户模拟端实际加载名）
- 版本变化：买入逻辑变化，升版本 v2.8（**仅模拟**；实盘模板未改）
- 修改内容：
  1. **server**：`fullpool_live` 每行打上 T-1 `limit_cnt_10d`（涨停定义与轨道 A gene 一致）。
  2. **QMT 轨道 B 模拟**：live 池下，只在 `money_flow_pass` 集合内按 `limit_cnt_10d` 降序取 **前 2**，仅这 2 只可走 P2 买入；**关闭 fallback 顶替**。缺字段则回退旧 FCFS。INIT 见 `v2.8` / `[LIM10]`。
- 原因/依据：B 专用因子回测 LIM10 T+1 **+2.55%** vs 旧 FCFS **+1.74%**（约 20 日，填仓 50% vs 60%）；A gene 不适配 B。用户确认模拟盘可部署验证「是否优于旧策略」。inbox `2026-09-03-track-b-native-factors-bt.md`。
- 验证：两 sim 文件 ASCII+ast；server 已部署。
- 部署：server **已部署**（明早/手动 `--fullpool-live` 带 lim10）。**需用户手动复制** QMT 模拟盘策略为 v2.8（`TrackB_track_b_qmt_auction_sim_v2.6.py` 或 `TrackB_track_b_qmt_auction_sim.py`）。实盘/TDX 不动。

## 2026-09-03 v2.34：Top10 基因重排 + MAX_CAND_RANK=3（方案 A，仅 QMT 轨道 A）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（candidates 导出增加 `_gene_rerank_candidates`）
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.33-tpl → v2.34-tpl，`MAX_CAND_RANK` 2→3）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.33 → v2.34，同上）
- 版本变化：卖出逻辑未改；买入资格变化，升版本 v2.34
- 修改内容：
  1. **server**：在写出 `{date}.candidates.json` 前，对 Top10 做池内基因+趋势重排：  
     `gene_score = rank(limit_cnt_10d) + rank(ma25_slope) + rank(ret_10d)`（全部 T-1 日线）。  
     重写 `rank=1..n`，保留 `rank_raw` / `gene_score` / `gene_parts`；JSON 增加 `rank_mode=gene_limit10_ma25slope_ret10`。  
     **资金不参与排序**（仍是买卖端硬门）。失败则原序降级。  
     **网页 recommendations / `{date}.json` 保序不动**（只改 candidates）。
  2. **QMT 轨道 A**：`MAX_CAND_RANK=3`——基因重排后的 rank 1–3 可进 P2；P2/资金门本身未改。
- 原因/依据：用户拍板方案 A。回测真实 34 日：gene≤3 能凑满 2 只 65%、WORST T+1 仍 +1.8%；≤2 过窄；≤5 池底 T+1 转负。inbox `2026-09-03-gene-window-long-revalidate.md`。
- 验证：QMT A 两文件 ASCII+ast；server 已部署并重导 `20260903.candidates.json`——新 top3=002328(raw5)/300413(raw1)/000796(raw4)；网页 Top2 导出仍为 300413/300319。
- 部署：server **已部署**（明早 cron 自动基因重排）。QMT 轨道 A 实盘+模拟 **需用户手动部署**（INIT 应见 `v2.34-tpl` / `v2.34`，`[RANK] max=3`）。TDX/ptrade/轨道 B 本次不改。

## 2026-09-03 v2.33：止盈（peel）在弱市不收紧，弱市侧只动止损/破位（仅 QMT 轨道 A）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.32-tpl → v2.33-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.32 → v2.33）
- 版本变化：v2.32 → v2.33（卖出逻辑变化，升版本；v2.31/v2.32 均未部署，**直接部署 v2.33**）
- 修改内容：撤掉弱市 peel 收紧（`pb × WEAK_PB_MULT`），删除常量 `WEAK_PB_MULT`，`[REGIME]` 日志改打 `(peel unchanged)`。弱市 regime 现在只动三处：**止损**（动态亏损下限 ×0.6）+ **持仓管理**（T+2 展期需现价 ≥ 25 日线；T+3 到帽仅跌破 25 日线才卖）。**止盈（peel 冲高回落、trail 移动止盈）与非弱市完全一致**。
- 原因/依据：用户 2026-09-03 14:34 明确「这个是止损卖出，止盈卖出维持原来不变」。peel ×0.7 与「趋势没破就拿住」原则冲突，撤除。
- 验证：两文件纯 ASCII + ast 通过；`pb * WEAK_PB_MULT` 零残留（WEAK_PB_MULT 仅存在于头注说明文字）。
- 部署：**需要用户手动部署** QMT 轨道 A 实盘 + 模拟（INIT 应打印 `v2.33-tpl` / `v2.33`）。server 端 market_env 已部署，无需再动。

## 2026-09-03 v2.32：弱市破位线改为 25 日均线（替代 v2.31 的当日 VWAP，仅 QMT 轨道 A）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.31-tpl → v2.32-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.31 → v2.32）
- 版本变化：v2.31 → v2.32（卖出逻辑变化，升版本；**v2.31 未部署过，直接部署 v2.32 即可**）
- 修改内容：弱市 regime 的「趋势是否破位」判定从**当日 VWAP** 改为 **25 日均线**（用户指定的趋势线）：
  1. 新增 `_ma25(C, code, today)`：QMT 日线 `get_market_data_ex(period="1d", count=31)` 取截至昨日的 25 日收盘均线（丢弃当日未完成 bar，与 `_wyckoff_distribution` 同约定）；按 (日, 股) 缓存，数据失败返回 None。
  2. `_weak_cap_sell_ok`：破位 = 现价 < MA25；**删除 ret<=0（水下）条款**——趋势是唯一标准，趋势完好即使浮亏也继续拿。MA25 不可得 → 沿用旧行为（到帽卖）。
  3. T+2 14:45 展期：现价 ≥ MA25 才展期（原为 ≥ 当日 VWAP）；MA25 不可得 → 展期（旧行为）。
  4. 新常量 `WEAK_TREND_MA = 25`；`[REGIME]`/`[EXT]` 日志改打 ma25。
  5. 不变：弱市 floor ×0.6 / peel ×0.7；`vwap_weak_early`（昨 VWAP 口径）不动；非弱市行为不变。
- 原因/依据：用户 2026-09-03 13:30 反馈——当日 VWAP 是日内线，「光破位」太严；短期趋势线应看 25 日均线，价格破 25 日线才算短期趋势破掉。
- 验证：两文件纯 ASCII + ast 通过；旧签名/旧日志零残留（脚本校验计数）。
- 部署：~~需要用户手动部署 v2.32~~ **v2.32 未部署即被 v2.33 取代（止盈不再收紧），请直接部署 v2.33**。server 端 `market_env` 今日已部署，无需再动。轨道 B / TDX / ptrade 不在本次范围。

## 2026-09-03 弱市破位敏感卖出 v2.31（仅 QMT 轨道 A）+ server 导出 market_env

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.30-tpl → v2.31-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.30 → v2.31）
  - `server/export_qmt_scores.py`（新增 `_market_env()`，三类导出 JSON 增加 `market_env` 字段）
  - `_port_weak_regime_v231.py`（移植脚本，本次仅用于 QMT A sim；B/TDX/ptrade 端口暂缓）
  - `_revert_weak_regime_3files.py`（回滚脚本，已把 TDX-A/ptrade 三文件恢复原样）
- 版本变化：A QMT live v2.30-tpl → v2.31-tpl；A QMT sim v2.30 → v2.31（卖出逻辑变化，升版本）；server 导出只加字段不改逻辑，不升版本
- 修改内容：
  1. **server**：`export_qmt_scores.py` 新增 `_market_env()`——全 A 主力净流入 5 日累计的全历史分位 → `state5_q`（1=深流出），`weak_regime=(q==1)`，口径与 `bt_research/bt_weak_winner_score.py` 一致；写入 `{date}.json` / `{date}.candidates.json` / `{date}.fullpool.json` / `{date}.fullpool_live.json`。计算失败返回 `{}`，不影响导出。
  2. **QMT 轨道 A（live+sim）**：读 candidates JSON 的 `market_env.weak_regime`（读不到=非弱市，行为与旧版一致）。弱市下：
     - 动态亏损下限 `_t2_force_floor` × `WEAK_FLOOR_MULT=0.6`（更紧）；
     - 冲高回落 peel `pb` × `WEAK_PB_MULT=0.7`（更紧）；
     - T+2 14:45 展期：仅当「趋势未破」（现价 ≥ 当日 VWAP）才展期，破位不展期（次日由既有 `vwap_weak_early` 处理）；
     - T+3 持有上限 `t2_force_after_extend`：仅当「已破位」（ret≤0 或现价 < 当日 VWAP）才强制卖，**趋势完好继续拿，不设硬时间剔除**。
  3. 非弱市 regime：所有行为与 v2.30 完全一致。
- 原因/依据：用户 2026-09-03 拍板「智能模型不应固定 T+N 硬性剔除，上涨趋势不破位就不该卖；按确认破位来」。回测依据 `knowledge/inbox/2026-09-03-weak-sell-tight-top2.md`：弱市（q=1）生产 Top2 T+1 +1.06% / T+5 −0.98%，利润在隔夜流失；非弱市提前退出亏机会成本。故不做时间闸，只做弱市破位敏感。
- 范围说明：用户明确「这次只改 QMT 轨道 A」。TDX-A / ptrade 三文件曾由移植脚本写入，已按用户指示回滚恢复原样；轨道 B 四文件从未被写入（移植脚本锚点未命中即跳过，未落盘）。后续要推广到 B/TDX/ptrade 时用 `_port_weak_regime_v231.py`（B 文件锚点需先人工核对）。
- 验证：QMT A live/sim 纯 ASCII + ast 通过；其余七文件 weak 标记=无、ast 通过（TDX/ptrade 允许 UTF-8）；服务器端 `_market_env()` 实测返回 `{'state5_q': 1, 'weak_regime': True, 'asof': '2026-09-02'}`；重跑导出后 `20260903.candidates.json` 已带 market_env，Top2 顺序不变（300413/300319）。
- 部署：server 部分**已部署**（`/home/ubuntu/alphapilot/export_qmt_scores.py`，明早 06:30/09:36 cron 自动带 market_env）。~~QMT 轨道 A 实盘/模拟两个文件需要用户手动部署~~ **v2.31 未部署即被 v2.32 取代（破位线 VWAP→25 日均线），请直接部署 v2.32**。未部署前交易端读不到 market_env 也无影响（按非弱市运行）。轨道 B / TDX / ptrade 本次不部署。

## 2026-09-02 Track B QMT 模拟端文件名 `_v2.6.py` 补 vwap 二次确认

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim_v2.6.py`（内部 v2.6 → v2.7；**文件名保持**，因 QMT 模拟端仍指向此名）
  - `_test_vwap_second_hit.py`（把该文件名加入回归）
  - `README.md`（目录表补一行，避免下次只改无后缀的 `TrackB_track_b_qmt_auction_sim.py`）
- 版本变化：v2.6 → v2.7（仅卖出：`vwap_weak_early` 二次确认）
- 修改内容：与归档 `TrackB_track_b_qmt_auction_sim.py` v2.7 对齐，只改 VWAP 早盘二次确认。第一次 09:35-09:50 仍低于 `vwap_ref` 只记 `[VWAP] first confirm wait 2nd`，同一分钟重轮询不算第二次，下一分钟仍低于才卖；涨回参考价撤销。持久化 `vwap_early_hits` / `vwap_early_min`。买点、仓位、rotation、t2_force、wyckoff_bc **未改**。
- 原因/依据：用户 QMT 模拟端加载的是带 `_v2.6` 后缀的文件，不是归档主文件。香农芯创式「窗口第一跳就卖」要在这个文件里停掉。
- 验证：该文件 ASCII+ast；`_test_vwap_second_hit.py` 含此路径
- 部署：**需要用户手动覆盖**轨道 B QMT **模拟**端同名文件。INIT 应打印 `track-B v2.7 (auction-select, vwap 2nd)`。盘中应先见 `wait 2nd`。轨道 B 实盘 / TDX / 轨道 A 不在本次部署范围。

## 2026-09-02 vwap_weak_early 二次确认（第一次不卖）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.29-tpl → v2.30-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.29 → v2.30）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.28 → v2.29）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（v2.6-tpl → v2.7-tpl）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.6 → v2.7）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（v1.17 → v1.18）
  - `ptrade/TrackA_track_a_ptrade_live.py`（v1.6-tpl → v1.7-tpl）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（v1.6 → v1.7）
  - `_test_vwap_second_hit.py`（新增）
- 版本变化：见上（卖出逻辑变化，升版本）
- 修改内容：`vwap_weak_early` 早盘窗口（09:35-09:50）第一次现价仍低于昨 VWAP 只记确认、打 `[VWAP] first confirm wait 2nd`，**不卖**。同一分钟内的重复轮询不算第二次。下一分钟仍低于昨 VWAP 才卖。涨回昨 VWAP 及以上仍撤销信号。新持久化字段 `vwap_early_hits` / `vwap_early_min`。
- 原因/依据：用户定调「不要第一次触发就卖，起码二次触发」。QMT 实盘 300475 香农芯创 09-02 09:36 第一跳卖在当日最低附近（165.62，当日低 165.04），09:45 已回 169.88。08-31 模拟盘同规则 3/3 卖飞。同一分钟不算第二次，避免 QMT/TDX 几秒一轮把同一次洗盘计成两次。
- 验证：QMT 四文件 ASCII+ast；TDX/ptrade ast；`_test_vwap_second_hit.py`；`_test_max_cand_rank.py`；`_test_hold_days_trading.py`
- 部署：**需要用户手动部署**轨道 A QMT 实盘/模拟 + TDX，以及轨道 B QMT 实盘/模拟 + TDX（若在跑）。Ptrade 未启用则启用时再导入。INIT 应为 A `v2.30-tpl` / `v2.30` / `v2.29`，B `v2.7-tpl` / `v2.7` / `v1.18`。盘中应先见 `wait 2nd`，下一分钟才可能 `vwap_weak_early`。

## 2026-09-01 Track A 关闭 rotation（满仓踢最弱）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.28-tpl → v2.29-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.28 → v2.29）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.27 → v2.28）
  - `ptrade/TrackA_track_a_ptrade_live.py`（v1.5-tpl → v1.6-tpl）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（v1.5 → v1.6）
- 版本变化：见上（卖出/腾仓逻辑变化，升版本）。INIT 与文件头同步。
- 修改内容：`ROTATION_ENABLE=False`。持仓满 4 只时不再卖掉最弱一只给新候选腾位；满仓则跳过新买，等正常卖出（t2_force / peel / vwap 等）腾位。rotation 函数保留，开关关掉即可恢复。轨道 B 未动。
- 原因/依据：rank<=2 后日均约 1 笔，几乎不需要踢仓；踢仓已有白卖（002058）和卖飞（TDX 002015 +8.3%）。T+0/T+1 本来就免疫 rotation（MIN_HOLD_DAYS=2），用户说的「T+1 清最差」对应这条腾仓路径。
- 验证：QMT ASCII+ast；`_test_max_cand_rank.py`；`_test_hold_days_trading.py`；`_test_rotation_v216.py`（测试内强制 ENABLE=True 覆盖 helper）
- 部署：**需要用户手动部署**轨道 A QMT 实盘/模拟 + TDX（与 rank<=2 一次部署即可）。INIT 应为 `v2.29-tpl` / `v2.29` / `v2.28`。轨道 B 不用部署。

## 2026-09-01 Track A 买入闸门 rank<=2（仍走 P2）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.27-tpl → v2.28-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.27 → v2.28）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.26 → v2.27）
  - `ptrade/TrackA_track_a_ptrade_live.py`（v1.4-tpl → v1.5-tpl）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（v1.4 → v1.5）
  - `track_a/_test_max_cand_rank.py`（新增离线测试）
- 版本变化：见上（买入资格逻辑变化，升版本）
- 修改内容：新增 `MAX_CAND_RANK=2`。`_check_buy` 入口先过滤 09:35 `candidates.json` 的 rank 1-2，再做甜蜜区重排 / rotation `worth_buy` / P2。rank 3+ 与缺 rank 不参赛。P2 规则本身未改。轨道 B 未动。
- 原因/依据：22 个可结算日 2026-07-27~08-31，rank<=2 T+1 +1.62% t=2.14 vs 全 Top10 +0.67%；实盘 08-28/08-31/09-01 买入均为 rank>=4 靠后票。用户确认落地 Top2，买入仍按 P2。
- 验证：QMT 两文件 ASCII + ast.parse；TDX/ptrade ast.parse；`_test_max_cand_rank.py`；`_test_hold_days_trading.py` 回归
- 部署：**需要用户手动部署**轨道 A QMT 实盘 + QMT 模拟 + TDX 模拟。Ptrade 未启用，启用时再导入。轨道 B 不用部署。重启后 INIT 应为 `v2.28-tpl` / `v2.28` / `v2.27`，盘中应见 `[RANK] max=2 keep=2/10`

## 2026-09-01 INIT 打印字符串与文件头版本对齐（不改逻辑）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（INIT print + 部署注释）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（INIT print）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（INIT log）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（INIT print + 部署注释）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（INIT print）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（INIT log）
  - `ptrade/TrackA_track_a_ptrade_live.py`（INIT log + 部署注释）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（INIT log）
- 版本变化：无（只改打印字符串，买卖逻辑不变）
- 修改内容：把各端 `[INIT]` 打印/日志里的版本号对齐到文件头当前版本：
  - 轨道 A QMT live `v2.24-tpl` → `v2.27-tpl`；sim `v2.24` → `v2.27`；TDX `v2.23` → `v2.26`
  - 轨道 B QMT live `v2.3-tpl` → `v2.6-tpl`；sim `v2.3` → `v2.6`；TDX `v1.14` → `v1.17`
  - Ptrade live `v1.2-tpl` → `v1.4-tpl`；sim `v1.2` → `v1.4`
  - live 文件尾「核对日志」注释同步改掉（A: `v2.19-tpl`→`v2.27-tpl`；B: `v1.9-tpl`→`v2.6-tpl`；ptrade: `v1.1-tpl`→`v1.4-tpl`）
- 原因/依据：多次升版本只改了文件头，忘了改 INIT 打印。用户截图确认 QMT 实盘编辑器已是 v2.27，但日志仍打 v2.24，造成版本误判。全端排查后其余 6 个交易端同样滞后。
- 验证：QMT 四文件 ASCII + ast.parse 通过；TDX/ptrade UTF-8 ast.parse 通过
- 部署：用户自行复制到对应交易端并重新编译/启动。部署后 INIT 应打印上表新版本号。不改买卖逻辑，不升版本号。

---

## 2026-08-31 `_hold_days` 改为交易日计数（8 文件全端对齐）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.26-tpl → v2.27-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.26 → v2.27）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.25 → v2.26）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（v2.5-tpl → v2.6-tpl）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.5 → v2.6）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（v1.16 → v1.17）
  - `ptrade/TrackA_track_a_ptrade_live.py`（v1.3-tpl → v1.4-tpl）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（v1.3 → v1.4）
  - `_test_hold_days_trading.py`（**新增**跨文件交易日语义测试）
  - `README.md`（目录版本号同步）
- 版本变化：八个文件均升版本号（改了持仓天数/卖出触发逻辑）
- 修改内容：
  1. **新增 2026 A 股休市表** `_ASHARE_CLOSED_2026`（元旦/春节/清明/五一/端午/中秋/国庆，含 09-25 中秋、10-01~10-07 国庆调休口径）。
  2. **新增 helper**：`_is_trading_day(d)`（剔除周末+休市表）、`_trading_days_between(b, t)`（开区间 `(b, t]`，买入日不计、今日计）。
  3. **`_hold_days` / `_hold_days_short` 改用交易日计数**：`(t - b).days`（日历天）→ `_trading_days_between(b, t)`。买入日 `%Y%m%d` 与 `YYYY-MM-DD` 兼容，缺/坏 `buy_date` 仍返回 999。
- 原因/依据：用户指出 **002466 天齐锂业（08-28 周五买，08-31 周一 = T+1 而非 T+2）** 的 T+1/T+2 口径错误。排查确认 `_hold_days` 用 `(t-b).days` 按**日历天**计：周五买→周一算出 hold=3，提前触发 `t2_force_after_extend`（天齐锂业 08-31 14:45 被卖）与 `rotation_sell`（002058 紫竹高科 08-31 14:22 被卖，实际只持有 1 个交易日）。修正后周五买→周一 hold=1（T+1）、周二 hold=2（T+2）。
- 验证：
  - 八文件语法校验通过（QMT 四端 ASCII+AST；TDX/ptrade 四端 UTF-8 AST）
  - 新增 `_test_hold_days_trading.py` **102/102 通过**（8 文件 × T+1/T+2/同日/跨周/跨国庆/999/交易日判定）
  - 既有回归：ptrade `_test_tracka_ptrade.py` 28/28、track_b `_test_sell_dynamic_v16.py` 18/18 通过
- 部署：**需重新部署 6 个在用/待用交易端**（用户手动，Agent 只更新本地权威版）：
  - A QMT 实盘 → `D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py`（明文复制）
  - B QMT 模拟 → `D:\国金QMT交易端模拟\python\AP全链交易模拟_TRACK_B.py`（QMT 客户端导入加密）
  - A TDX → `D:\new_tdx_mock\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim.py`（明文复制）
  - B TDX → `D:\new_tdx_mock\PYPlugins\user\TrackB_track_b_tdx_auction_sim.py`（明文复制）
  - B QMT 实盘 `TrackB_track_b_qmt_auction_live.py` v2.6-tpl（live B 未启用，**已同步改**，启用时导入）
  - A QMT 模拟 `TrackA_track_a_qmt_full_chain_sim.py` v2.27（A sim 未在用，**已同步改**，启用时导入）
  - Ptrade live/sim v1.4 / v1.4-tpl（Ptrade 端未启用，**已同步改**，启用时导入）

---

## 2026-08-31 vwap_weak_early 次日确认改造（8 文件全端对齐）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.25-tpl → v2.26-tpl）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.25 → v2.26，**本轮补改**）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.24 → v2.25）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（v2.4-tpl → v2.5-tpl，**本轮补改**）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.4 → v2.5）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（v1.15 → v1.16）
  - `ptrade/TrackA_track_a_ptrade_live.py`（v1.2-tpl → v1.3-tpl，**本轮补改**）
  - `ptrade/TrackA_track_a_ptrade_sim.py`（v1.2 → v1.3，**本轮补改**）
  - `track_b/_test_sell_dynamic_v16.py`（补 [10]/[11] 确认路径用例）
  - `README.md`（目录版本号同步）
- 版本变化：八个文件均升版本号（改了卖出逻辑）
- 修改内容：
  1. **置位时记录参考 VWAP**：`vwap_broken` 置位时新增 `pos["vwap_ref"] = vw`（当时 day-VWAP）。
  2. **次日早盘加确认**：09:35-09:50 窗口内，若现价 `price >= vwap_ref`（已收复参考价）→ **撤销信号**（`vwap_broken=False`, `vwap_ref=0`，`[VWAP] recovered ... cancel weak-early`），继续持有；仅当现价仍 `price < vwap_ref` 才触发 `vwap_weak_early` 卖出。
  3. **新字段持久化**：`vwap_ref` 加入各端 `POS_STATE_PERSIST` + `_merge_pos_state` 数值恢复，重启不丢参考价。
  4. 兼容：旧 `pos_state.json` 无 `vwap_ref` → `vwap_ref=0` → 走 else 卖出分支，行为等同旧版无条件卖，无回退风险。
- 原因/依据：QMT 模拟 08-31 `vwap_weak_early` 首次真实触发 3/3 全部卖飞（000700 卖 11.20→最高 11.43 / 002292 8.16→8.40 / 003032 10.22→10.71）。全端排查 + 11 信号回测：次日收盘卖 vs 早盘无条件卖均值 +2.32%。用户明确要求**全部文件统一对齐**（"到时候忘记了这个没改、那个没改的，要改就统一改"），故未启用的 B QMT 实盘 / A QMT 模拟 / Ptrade live+sim 也一并同步改动，避免将来启用时漏改。详见全局 inbox `2026-08-31-all-terminals-sell-early-sweep.md` / `2026-08-31-b-track-vwap-weak-early-sell-too-early.md`。
- 验证：八文件 ASCII+AST 校验通过（QMT 四端 `b.decode('ascii')` + `ast.parse` 全绿；TDX/ptrade 四端 `ast.parse` 通过）；B 轨离线测试 `_test_sell_dynamic_v16.py` 18/18 通过（含新增 [10] 收复撤销 / [11] 仍弱触发两用例）
- 部署：**需重新部署 6 个在用/待用交易端**（用户手动，Agent 只更新本地权威版）：
  - A QMT 实盘 → `D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py`（明文复制）
  - B QMT 模拟 → `D:\国金QMT交易端模拟\python\AP全链交易模拟_TRACK_B.py`（QMT 客户端导入加密）
  - A TDX → `D:\new_tdx_mock\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim.py`（明文复制）
  - B TDX → `D:\new_tdx_mock\PYPlugins\user\TrackB_track_b_tdx_auction_sim.py`（明文复制）
  - B QMT 实盘 `TrackB_track_b_qmt_auction_live.py` v2.5-tpl（live B 未启用，**已同步改**，启用时导入）
  - A QMT 模拟 `TrackA_track_a_qmt_full_chain_sim.py` v2.26（A sim 未在用，**已同步改**，启用时导入）
  - Ptrade live/sim v1.3 / v1.3-tpl（Ptrade 端未启用，**已同步改**，启用时导入）

---

## 2026-08-29 约定固化：Agent 只更新本地权威版，部署由用户手动执行

- 修改人/Agent：主控 Agent
- 涉及文件：`production_strategies/README.md`（规则第 6 条改）、`.cursor/rules/production-strategies.mdc`（硬性规则第 5 条改）
- 版本变化：无（规则/文档变更）
- 修改内容：
  1. **规则明确**：Agent 只更新 `production_strategies/` 内的文件（本地权威版），**不再直接写交易端文件**（QMT python 目录 / TDX `PYPlugins\user`）。部署由用户手动执行（复制/导入到 QMT 和通达信）。
  2. **记录今晚误操作**：2026-08-29 19:43 曾直接复制 5 个明文文件到交易端（A QMT 实盘/模拟、A TDX、B TDX，备份 `.bak_20260829_1943xx`）。此后不再做此动作。B 端 QMT 实盘/模拟是 QMT 加密密文，需用户 QMT 客户端导入（见下方 19:45 部署记录）。
- 原因/依据：用户明确要求"以后你只要把文件更新在本地上就可以了，我会去通达信和 QMT 部署的"。之前 README 第 6 条只写"部署：从本文件夹复制到对应交易端"，未明确由谁执行，导致 Agent 直接复制交易端。
- 验证：README + 规则文件已同步更新
- 部署：**用户手动执行**（本机 QMT/TDX）。待部署清单见下方 19:45 条。

---

## 2026-08-29 甜蜜区部署到交易端（6 端对齐的最后一步）

- 修改人/Agent：主控 Agent
- 涉及文件：交易端明文文件（已直接覆盖部署）+ B 端 QMT 密文文件（需用户 QMT 客户端导入）
- 版本变化：无（是部署动作，非代码修改）
- 修改内容：
  1. **已直接覆盖部署（备份 `.bak_20260829_1943xx` 已生成）**：
     - A QMT 实盘 `D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py` → v2.25-tpl
     - A QMT 模拟 `D:\国金QMT交易端模拟\python\AP全链交易模拟_TRACK_A.py` → v2.25
     - A TDX `D:\new_tdx_mock\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim.py` + `TrackA_tdx_full_chain.py` → v2.24
     - B TDX `D:\new_tdx_mock\PYPlugins\user\TrackB_track_b_tdx_auction_sim.py` → v1.15
     - 校验：部署后文件 md5 与权威版一致、含 `SWEET_ZONE_MODE = 1` ✅
  2. **需用户手动操作（QMT 客户端导入）**：
     - B QMT 实盘 `D:\国金证券QMT交易端\python\AP全链路交易_TRACK_B.py` 是 **QMT 加密密文**（非明文），无法直接覆盖
     - B QMT 模拟 `D:\国金QMT交易端模拟\python\AP全链交易模拟_TRACK_B.py` 同上
     - 动作：在 QMT 客户端中删除旧策略 → 新建策略指向明文文件 `production_strategies/track_b/TrackB_track_b_qmt_auction_live.py`（v2.4-tpl）和 `TrackB_track_b_qmt_auction_sim.py`（v2.4），QMT 会自动加密保存
- 原因/依据：融合 IC 目标链路的最后阻塞点=交易端仍跑旧版（A QMT v2.23-tpl、A sim v2.23、TDX v2.22，均无甜蜜区、无 v2.24 卖出回读分能力）。明文文件按生产规则直接复制；B 端 QMT 密文只能用户 QMT 客户端导入。
- 验证：部署后 4+1 个明文文件 md5 一致 + SWEET 检查通过
- 部署：**全部交易端都需重启策略生效**（QMT 重启策略 / TDX 重启运行）。B 端 QMT 必须先完成客户端导入再重启。
- 周一 08-31 验收：重启后各端日志应出现 `[INIT] ... v2.2X` 版本号；买入日志带 ` SWEET` 标签；平仓写 `fusion_closed_trades.jsonl`。

---

## 2026-08-29 轨道 B QMT LIVE 甜蜜区对齐（补齐 Track B 最后一处）

- 修改人/Agent：主控 Agent
- 涉及文件：`production_strategies/track_b/TrackB_track_b_qmt_auction_live.py`
- 版本变化：v2.3-tpl → **v2.4-tpl**（逻辑变化：P2 甜蜜区触发优先级，与 sim v2.4 对齐）
- 修改内容（4 处，均与 `TrackB_track_b_qmt_auction_sim.py` v2.4 一致）：
  1. 常量区新增 `SWEET_ZONE_MODE=1` / `SWEET_GAP_LO=-1.5` / `SWEET_GAP_HI=0.0`（含 BT 依据注释）
  2. 新增 `_is_sweet_zone` / `_order_by_sweet` 两个函数（Track B 用 `_gap_cache`/`_get_gap_pct` 取竞价 gap）
  3. `_check_buy` 的 `picked` 排序：每个 tier（money_pass 优先/fallback）内 `_order_by_sweet` 重排
  4. BUY 日志加 `sweet_tag = " SWEET" if _is_sweet_zone(...) else ""`
- 原因/依据：用户问"轨道 A 和轨道 B 也都改了吗、都对齐了吗"。盘点发现 Track B QMT live 是 v2.3-tpl **缺甜蜜区**（Track A 在 18:40 已补齐 live v2.25-tpl，Track B 的 sim v2.4/TDX sim v1.15 已有）。本次补齐 Track B 最后一块，使 A/B 全部 6 个文件甜蜜区对齐。
- 验证：四个代码块与 sim 提取对比**一致**（仅 docstring 版本号 tpl 差异，符合模板惯例）；ASCII 校验通过（QMT 要求纯 ASCII）；语法校验通过
- 部署：**需要重新部署到 Track B QMT 实盘**（live 模板，每个实盘账户各一份，只需改 CONFIG 块账号信息）。周一开盘前完成重启生效。

---

## 2026-08-29 QMT LIVE 甜蜜区对齐（用户要求实盘/模拟一致）

- 修改人/Agent：主控 Agent
- 涉及文件：`production_strategies/track_a/TrackA_track_a_qmt_full_chain_live.py`
- 版本变化：v2.24-tpl → **v2.25-tpl**（逻辑变化：P2 甜蜜区触发优先级，与 sim v2.25 对齐）
- 修改内容（4 处，均与 `TrackA_track_a_qmt_full_chain_sim.py` v2.25 逐字节一致）：
  1. 常量区新增 `SWEET_ZONE_MODE=1` / `SWEET_GAP_LO=-1.5` / `SWEET_GAP_HI=0.0`（含 BT 依据注释）
  2. 新增 `_sweet_gap_pct` / `_is_sweet_zone` / `_order_cands_by_sweet` 三个函数
  3. `_check_buy` 入口加 `cands = _order_cands_by_sweet(C, cands)`（触发排序优先级，不改打分）
  4. BUY 日志加 `sweet_tag = " SWEET" if _is_sweet_zone(...) else ""`
- 原因/依据：用户要求"把甜蜜区代码和 QMT 实盘和模拟对齐"。此前甜蜜区只加在 sim（v2.25）/TDX sim（v2.24），live 模板（v2.24-tpl）未加——live 历史性落后 sim 的 P2 功能。本次把 live 补齐到与 sim 完全一致，保证实盘与模拟触发行为一致。
- 验证：四个代码块与 sim 提取对比**逐字节 IDENTICAL**（版本号归一后）；ASCII 校验通过（QMT 要求纯 ASCII）；语法校验通过
- 部署：**需要重新部署到 QMT 实盘**（live 模板，每个实盘账户各一份；只需改 CONFIG 块账号信息）。周一开盘前完成重启生效。
- 注意：`SWEET_ZONE_MODE=1`（priority 模式）与 sim 一致；QMT sim 若此前已部署 v2.25 无需再动。

---

## 2026-08-29 融合 IC 学习引擎防回填污染修复（周六复核发现）

- 修改人/Agent：主控 Agent
- 涉及文件：`production_strategies/server/fusion_scorer.py`（权威版）；服务器 `/home/ubuntu/alphapilot/fusion_scorer.py`；服务器数据文件 `output/feedback/model_weights.json`、`data/kelly_learner_trades.json`
- 版本变化：无（学习引擎 bug 修复，不改策略版本号）
- 修改内容（3 处）：
  1. **`fusion_scorer.update_ic_weights` 增加 backfill 过滤**：`if t.get("backfill"): continue`（在样本筛选最前面）。学习引擎只能用**真实平仓盈亏**（无 backfill 标记）更新权重；回填样本是手工/历史导入，混入会污染 IC 与 EMA 权重。
  2. **重置被污染的 `model_weights.json`**：实测服务器权重已被 backfill 污染——`updated_at 2026-08-28T18:09:18`，权重从默认 `{0.5,0.3,0.2}` 漂移到 `{0.2477,0.3769,0.3755}`（11 条 backfill 算出的错误负 IC 拉偏）。已重置回默认 `{0.5,0.3,0.2}`、`n_samples=0`、`rolling_ic={}`，污染版备份 `.bak_backfill_polluted_20260829`。
  3. **清理端到端测试假样本**：`data/kelly_learner_trades.json` 里发现一条无 backfill 标记的测试记录（600519, pnl=500, 无 source/sell_time，来自之前端到端验证），已删除，备份 `.bak_pre_clean_20260829`。修复前它会混进 IC 窗口（n_used=1）。
- 原因/依据：周六复核服务器 `run_feedback_loop.py`（16:15 cron）时，发现 `update_ic_weights` 只过滤"无 `_fusion_scores` 或 pnl=0"的样本，**不排除 `backfill=True`**。本地 `fusion_closed_trades.jsonl` 11 条全带 backfill 且 pnl≠0 → 周一 16:15 会把回填样本当实盘盈亏更新权重，直接违背目标"用实盘盈亏更新"。
- 验证：
  - 本地逻辑测试：11 backfill + 2 真实 → `n_used=2`、保持默认权重；11 backfill + 5 真实 → `n_used=5`、EMA 正常更新、权重和=1 ✅
  - 服务器 dry-run（`run_feedback_loop.py --no-retrain`）：清理前 `n_used=1`（测试样本混入）→ 清理后 `n_used=0`（11 backfill 全排除），`model_weights.json` 保持默认 `n_samples=0` ✅
  - 服务器编译通过；修复行已 grep 确认就位 ✅
- 部署：**已部署服务器**（08-29 18:3x），备份 `fusion_scorer.py.bak_no_backfill_filter_20260829`。无需交易端动作。
- 周一 08-31 验收：16:15 后 `python scripts/check_fusion_ic_checkpoint.py --pull-server`，应见 `jsonl_live_new>0`（真实平仓）且 `model_weights.json` 的 `n_samples` = 真实平仓笔数（不含 11 条 backfill），权重从默认值按真实 IC 移动。

---

## 2026-08-29 凌晨预检门增强：margin/lhb 对齐检查 + 多轮重试 cron（"拿不到怎么办"）

- 修改人/Agent：主控 Agent
- 涉及文件：服务器生产文件 `/home/ubuntu/alphapilot/scripts/preflight_checkpoint.py`；服务器 crontab
- 版本变化：无（运维/数据防护，不改策略版本号）
- 修改内容：
  1. `preflight_checkpoint.py` 新增 `_aux_asof_checks()`：
     - **margin_stale**：`margin_data.json` mtime 距今 >7 天 → fail（连续拉取失败文件滞留）
     - **lhb_stale**：`lhb_history.json` 最新日落后 K线 ≥2 交易日 → fail（龙虎榜拉取连续失败）
     - 关键口径：两融/龙虎榜都是 **T+1 公布 + 凌晨 04:40/04:45 拉取**，因此 00:30 预检时天然是 T-1 数据——检查只拦"异常滞留"，不拦"正常 T-1"（避免每天误报）。
  2. cron 增补多轮重试：`00:30 首检 → 01:30 复检 → 02:30 二次重试`，04:50 闸门兜底。preflight 幂等：pass 静默，fail 企微（已按天+签名去重，不重复轰炸）。
- 原因/依据：用户问"04:40/04:45/04:52 链路的数据 00:30 能拿到吗？拿不到怎么办？"。实测答复：**fund_flow 00:30 是当天的**（21:00 主任务已写当日，mtime 08-28 21:00 实测）；**margin/lhb 00:30 天然是 T-1**（T+1 公布 + 凌晨拉取），这是正常口径不是异常。真正"拿不到"= 文件缺失 / 结构坏 / 连续拉取失败滞留 → 预检门立即企微 + 自动重拉，01:30/02:30 自动重试，04:50 闸门最终兜底。
- 验证：服务器实跑 16 项 checkpoint 全 ✅（新增 margin_stale/lhb_stale）；lhb=2026-08-28 == kline=2026-08-28 正确判定；四源对齐（K线/筹码/资金流/龙虎榜）展示完整；三跳 cron 确认存在（00:30/01:30/02:30）。
- 部署：**已部署服务器**（08-29 15:33），cron 三条 preflight 已确认。无需交易端动作。
- 周一 08-31 验收：`output/logs/preflight.log` 应有 00:30/01:30/02:30 三条记录，全 ✅。

---

## 2026-08-29 数据契约防护 + 凌晨预检门上线（08-24 事故防复发）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - 服务器生产文件：`/home/ubuntu/alphapilot/scripts/data_readiness_gate.py`、`/home/ubuntu/alphapilot/scripts/preflight_checkpoint.py`（新增）、`/home/ubuntu/alphapilot/alphapilot_pipeline_v3.py`
  - 本地模板：`production_strategies/server/_upload_chip_template.py`
- 版本变化：无（运维/数据防护，不改策略版本号）
- 修改内容（四层防线 + 一道预检门）：
  1. `data_readiness_gate.py` 新增 `check_chip_consumer_contract`：兼容路径解出记录数 <4000 或最新日覆盖 <90% → fail（结构不可解/半截上传）。加入 `build_report`。
  2. `train_v25.py` 训练前 fail-fast：非 smoke 模式筹码覆盖 <50% → return 1 拒绝训练（宁可当天不重训，不训练垃圾模型）。
  3. `vm25_scorer.py` 加载后 chip<1000 条打印醒目告警。
  4. `_upload_chip_template.py` 上传前用消费者路径验证，解出 <4000 只 → **禁止上传**。
  5. **新增 `scripts/preflight_checkpoint.py`（凌晨预检门，00:30 cron）**：复用 `data_readiness_gate` 全部检查逐条输出 checkpoint，失败自动重拉（复用 try_repair），企微告警（fail-only 去重），写 `output/preflight_checkpoint.json`；`alphapilot_pipeline_v3.py` 05:00 读取该文件打印预检门状态（不阻断）。
- 原因/依据：08-24 筹码事故根因是「检查器比消费者宽容」——`_chip_records` 兼容 `{ok,data}` 包装通过，但 `train_v25/vm25_scorer` 取顶层读不到，静默降质 5 天。用户要求防复发 + 凌晨预检门（05:00 前逐条验证、失败即刻告警 + 自动重拉）。原本 04:50 闸门发现问题后距 05:00 仅 10 分钟，提前到 00:30 有 5 小时修复窗口。
- 验证：
  - 契约检查三场景：真实 `{ok,data}`→ok(4992只)；平铺→ok；半截(100只)→fail ✅
  - train_v25 fail-fast：破损 chip_cov=0.02%→拒绝；正常 99.8%→允许 ✅
  - vm25_scorer：真实 load chip=4992；破损<1000 告警 ✅
  - 服务器实跑 preflight：14 项 checkpoint 全 ✅，对齐 K线/筹码/资金流 三源 08-28 一致，json ready=True ✅
- 部署：**已部署服务器**（08-29 15:20），备份 `data_readiness_gate.py.bak_contract_20260829` / `train_v25.py.bak_contract_20260829` / `vm25_scorer.py.bak_contract_20260829` / `alphapilot_pipeline_v3.py.bak_preflight_20260829`。cron 新增 `30 0 * * 1-5 preflight_checkpoint.py`（04:50 data_readiness_gate 保留为二次确认）。无需交易端动作。
- 周一 08-31 验收：00:30 预检日志 `output/logs/preflight.log` 应全 ✅；04:50 `data_readiness.json` 的 `chip_consumer_contract.level` 应 ok。

---

## 2026-08-29 每日重训 chip 数据结构兼容修复（生产训练/打分核心，非本目录文件）

- 修改人/Agent：主控 Agent
- 涉及文件（服务器生产文件，非 `production_strategies/` 轨道策略）：
  - `/home/ubuntu/alphapilot/train_v25.py`（每日 21:30 滚动重训）
  - `/home/ubuntu/alphapilot/vm25_scorer.py`（05:00 管线 / 09:35 scanner 生产打分）
- 版本变化：无（逻辑修复，不改策略版本号）
- 修改内容：`chip_data_all.json` 自 08-24 起被本地上传模板写成 `{ok: True, data: {...}}` 包装结构；`train_v25.py`/`vm25_scorer.py` 直接取顶层导致筹码 6 维特征全空。两处 CHIP/chip 加载改为 `_raw.get("data", _raw)` 兼容包装（与 `features.py` 一致）。
- 原因/依据：08-29 自我学习机制全量审计发现——重训 AUC 08-24 起 0.7221→0.707 连续 5 天被 AUC 安全门拒绝，根因即 chip 结构变化（训练特征 77→82 维、筹码覆盖 0%）；生产打分 `_merge_chip` 同路径受损。
- 验证：AST 通过；服务器 smoke 重训筹码覆盖 0→100%、特征维 77→82、`z_chip_concentration` 等 6 特征全部 `[✓]`；vm25_scorer load `chip count 4992`、模型 106 维正常。
- 部署：**已部署服务器**（08-29 14:23），备份 `train_v25.py.bak_chipfix_20260829` / `vm25_scorer.py.bak_chipfix_20260829`。无需交易端动作。
- 周一 08-31 21:30 重训后验收：`retrain_status.json` 的 `auc_gate.passed` 应 True 或训练日志筹码覆盖 100%。

---

## 2026-08-29 RD IC 历史清理：保留真值，清除 13 天假 0（周六预检）

- 修改人/Agent：主控 Agent
- 涉及文件（服务器数据文件，非代码）：`output/feedback/history.jsonl`
- 版本变化：无（数据清理）
- 修改内容：将 RD 调权 IC 历史从 13 行重建为 7 行真值。保留 ICIR 非零 7 天（08-11/12/13/14/18/20/21，基于真实 `ml_score`，口径与修复后一致）；删除全部假 0（字段 bug 恒值：MOMENTUM/HEAT/PIPELINE 13 天全 0、ICIR 6 天 0）。原文件备份为 `history.jsonl.bak_20260829`。
- 原因/依据：修复前字段映射 bug 导致 MOMENTUM/HEAT/PIPELINE 恒 0、资金轨路径日（08-25~28）ICIR 也假 0。若保留会污染新调权窗口（占窗口名额、拉低均值）。ICIR 7 天真值可复用，让周一起 IC 窗口从 7 个真实样本起步。
- 验证：服务器重建成功（7 行）；`auto_tune` 实测读入 `ICIR=7 值`，均值 +0.04 但符号 4正3负（57%<60%）不触发调权——正确保守行为；MOMENTUM 历史清空从周一重新积累。
- 部署：无需（历史数据文件已重建）

---

## 2026-08-29 融合 IC 学习引擎脚本补入权威归档（周六预检）

- 修改人/Agent：主控 Agent
- 涉及文件（归档，无服务器改动）：
  - `server/run_feedback_loop.py`（16:15 反馈闭环主脚本，新增归档）
  - `server/fusion_scorer.py`（三路融合 IC 权重更新器，新增归档）
- 版本变化：无（服务器 08-28 已部署，本次仅补归档）
- 修改内容：将融合 IC 学习链路的两个服务器脚本从「仅部署未归档」补入 `production_strategies/server/`，作为唯一权威来源。本地 `scripts/run_feedback_loop.py`、根目录 `fusion_scorer.py` 与服务器 md5 全一致。
- 原因/依据：生产策略归档规则要求所有落地生产代码进 `production_strategies/`；此前融合 IC 部署（08-28 CHANGELOG）漏归档这两个学习引擎。
- 验证：md5 本地=服务器=归档一致（`0517f051…` / `3984901d…`）；`update_ic_weights` 逻辑已通读：筛选 `_fusion_scores.vm25` 非空 + pnl 非零 → Spearman IC → EMA(α=0.10) 更新 → 归一化 → 写 `output/feedback/model_weights.json`（含 `updated_at`/`n_samples`）。
- 部署：无需（服务器已是同款运行中）

---

## 2026-08-29 RD 自动调权修复：空转闭环 → 真正影响 09:35 资金轨排序

- 修改人/Agent：主控 Agent
- 涉及文件（服务器选股模型，非交易端策略）：
  - `scripts/feedback_auto_tune.py`（服务器 16:15 自动调权）
  - `live_momentum_scanner.py`（服务器 09:35 资金轨 scanner）
- 版本变化：无版本号（服务器脚本）；逻辑变更
- 修改内容：
  1. **字段映射修正**：旧代码读 `momentum_score`/`sector_heat_hit`/`pipeline_hit`，`daily_recommend.json` 实际无这些字段 → 三因子 IC 恒 0。改为自适应两种路径字段：主路径（池≥100）`ml_score`/`_live_momentum_z`/`_pipeline_z`；资金轨（池<100）`_icir_z`/`_momentum_z`（新增落盘）。
  2. **调权规则放宽**：连续 5 天同向（几乎不触发）→ 近 10 天窗口均值 |IC|≥0.03 且符号占优 ≥60%、至少 5 个有效日；无效日（样本不足/恒值）不再写假 0 IC。
  3. **只调真实消费参数**：旧代码调 `W_HEAT`/`W_PIPELINE`/`SURGE_ARM_B_MULT`，scanner 无消费点 = 空转。现只调 `W_ICIR`/`W_MOMENTUM`（资金轨 final=icir_z×W_ICIR+momentum_z×W_MOMENTUM 的直接排序权重），其余保留固定值写 env。
  4. **scanner 接线**：`W_ICIR`/`W_MOMENTUM` 从 `config/feedback_params.env` 读取（16:15 写入，09:35 读取；文件缺失回退 0.50/0.50，行为不变）。资金轨 rec 落盘 `_icir_z`/`_momentum_z` 供调权算 IC。
- 原因/依据：用户核查发现 RD 空转（08-26/27/28 历史 IC 全 0、changes 恒 []、调权输出无人消费）。`knowledge/inbox/2026-08-29-rd-auto-tune-no-progress.md`。
- 验证：
  - 本地：auto_tune 上调/下调/样本不足三场景单元测试全过；真实数据 08-14 四因子 IC 非 None
  - 服务器：语法 OK；08-28 资金轨 rec 模拟 `_icir_z`/`_momentum_z` 落盘后 ICIR/MOMENTUM IC 非 None，调权可触发
- 部署：**已 scp 到服务器** `/home/ubuntu/alphapilot/`（cron 16:15 自动生效，scanner 09:35 自动读 env，无需重启）。边界：主路径（池≥100）排序权重 0.6/0.4 硬编码不受调权影响；RD 调权当前只作用池<100 资金轨路径

---

## 2026-08-29 P2 甜蜜区：影子记录 + 轨道 A/B 模拟盘整合

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `scripts/reversal_shadow_scanner.py`（新增 P2 候选甜蜜区标签 + mootdx 补拉）
  - `scripts/reversal_shadow_report.py`（新增 P2 甜蜜区 vs 非甜蜜区结算 + 企业微信推送）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.24→v2.25）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.23→v2.24）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v2.3→v2.4）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（v1.14→v1.15）
- 版本变化：四份模拟盘买入排序逻辑升版；影子脚本无版本概念
- 修改内容：
  1. **服务器影子**：scanner 每日读 `output/qmt_scores/{date}.candidates.json`（Top10 P2 候选），用 kline 当日 open_gap 打甜蜜区标签（gap∈[-1.5%,0]），全市场拉取漏掉的候选用 mootdx 单独补拉；写入 `reversal_shadow_history.jsonl` 的 `p2_candidates` 键。report 在 T+1 结算时对比甜蜜区 vs 非甜蜜区胜率/平均收益，追加到企业微信 markdown。
  2. **轨道 A/B 模拟盘**：新增 `SWEET_ZONE_MODE`（0=off / 1=priority / 2=only，默认 1）。仅触发时**排序优先**（不改 P2 打分）：QMT 端按 `_get_quote` 的 open/prev 算 gap，TDX 端按 snapshot Open/LastClose 算 gap；买入日志标 `[SWEET]`。轨道 A 在 `_check_buy` 候选遍历前重排；轨道 B 在 money_pass/fallback 层内重排。
- 原因/依据：P2 甜蜜区（轻微低开 -1.5%~0）在回测（2026-04~07 合成 + 07~08 实盘）显示 T+1 向上偏置（7/7 切片 ≥），用户确认作为触发优先级整合；先影子积累真实样本 + 模拟盘验证，不动实盘
- 验证：QMT 两文件 ASCII+ast 通过；TDX UTF-8 ast 通过；`_test_sweet_zone.py` 单元测试（边界/优先级/only/off/gap 缺失）全过；服务器 08-21 实测 P2 候选 10/10 gap 可得、6 只甜蜜区
- 部署：**影子脚本已部署服务器**（cron 14:50/16:30 不变）。**四份 sim 待复制到交易端**（QMT 模拟盘 python 目录、TDX `PYPlugins\user`）并重启策略。live 模板未动（等模拟验证后再同步）

---

## 2026-08-29 尾盘超跌×低开影子 scanner 部署服务器

- 修改人/Agent：主控 Agent
- 涉及文件：`scripts/reversal_shadow_scanner.py`、`scripts/reversal_shadow_report.py`（本地仓库已有）；`docs/REVERSAL_SHADOW_DEPLOY.md`（状态更新）
- 版本变化：无（影子旁路，不改 P2 任何链路）
- 修改内容：通过 srv_ssh 自动通道部署到服务器 `/home/ubuntu/alphapilot/scripts/`；cron 加两行（14:50 scanner、16:30 report）；冒烟测试 `--date 2026-08-28 --pool-file` 通过（弱市 OFF 无候选为预期）；crontab 136→138 行双重验证 + 备份
- 原因/依据：路径 C 影子先行，只记录不对单，积累样本外 T+1 结算数据
- 验证：服务器 `py_compile` 通过；scanner 冒烟出分位边界/大盘开关/落盘正常
- 部署：已部署服务器，cron 生效；企业微信推送依赖服务器已有 `config/wecom_webhook.conf`

---

## 2026-08-28 卖出写 jsonl：持仓没分则回读买入日 candidates

- 修改人/Agent：主控 Agent
- 涉及文件：`track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.23-tpl→v2.24-tpl）、`track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.23→v2.24）、`track_a/TrackA_track_a_tdx_full_chain_sim.py`（INIT v2.22→v2.23）
- 版本变化：买卖记账补丁，不改 P2 / 不改选股顺序
- 修改内容：`_append_fusion_closed` 若 `pos.fusion_scores` 缺失，按 `buy_date` 读 `C:\alphapilot\scores\{date}.candidates.json` 再组三路分。盘后给 `20260828.candidates.json` 补打了 `fusion_scores`（10/10，顺序未改，asof 仍 09:55）
- 原因/依据：融合 IC 目标要求平仓进 jsonl；QMT 若覆盖掉盘后补打的 pos_state，卖出会静默跳过
- 验证：QMT 两文件 ASCII+ast 通过；TDX UTF-8 ast 通过。服务器 candidates 顺序仍是 002428, 002396, 002155...
- 部署：**已复制**到 QMT 实盘 / QMT 模拟 / TDX 两份。**仍须重启策略**。融合排名已否决，不改序

---

## 2026-08-28 本机融合平仓 jsonl 16:10 同步到服务器

- 修改人/Agent：主控 Agent
- 涉及文件：`scripts/sync_fusion_closed_to_server.py`（新增）；Windows 计划任务 `AlphaPilot_sync_fusion_closed`
- 版本变化：无
- 修改内容：发现 16:15 服务器 cron 读不到 Windows 的 `C:/alphapilot/fusion_closed_trades.jsonl`。新增同步脚本，工作日 16:10 推到 `/home/ubuntu/alphapilot/data/fusion_closed_trades.jsonl`。服务器 16:15 已是 `run_feedback_loop.py --no-retrain`（融合 IC）；同分钟 `feedback_auto_tune.py` 仍是 RD scanner IC。
- 原因/依据：没有这条链路，新买入平仓永远进不了 `model_weights.json`
- 验证：脚本已成功 sync n=11；任务下次运行 2026-08-31 16:10
- 部署：Windows 任务已创建。交易端仍须重启。融合排名未前移

---

## 2026-08-28 用 candidates.json 扩大三端回填并手动更新融合权重

- 修改人/Agent：主控 Agent
- 涉及文件：`scripts/backfill_fusion_closed_trades.py`（优先读 `C:/alphapilot/scores/{date}.candidates.json`）；服务器 `data/fusion_closed_trades.jsonl` + `output/feedback/model_weights.json`
- 版本变化：无（回填脚本，不改买卖/选股判定）
- 修改内容：回填从档案 picks 改为同一套选股模型的 Top10 candidates；得到 11 笔（1 qmt_sim + 10 tdx_sim）；上传服务器后手动 `update_ic_weights`，n_samples 7→11
- 原因/依据：用户定调三端样本通用；原回填只对上 4 笔
- 验证：服务器 `model_weights.json` updated_at=2026-08-28T18:01:53，ok=true，n_used=11
- 部署：jsonl 已在服务器。16:15 cron 下交易日会再跑。交易端仍须重启才能把开仓分带进卖出 jsonl。融合排名未前移

---

## 2026-08-28 口径：轨道 A 三端融合 IC 样本通用

- 修改人/Agent：主控 Agent
- 涉及文件：知识库（无生产代码改动）
- 版本变化：无
- 修改内容：用户定调 —— 选股模型融合 IC 把 QMT 实盘 / QMT 模拟 / 通达信模拟当成同一批样本。融合排名前移仍未做，原因不是「模拟不能用」。
- 原因/依据：三端都读同一份 candidates.json
- 验证：写入 checkpoints / selection_vs_execution / decisions
- 部署：交易端无需因本口径再改代码

---

## 2026-08-28 建立 Checkpoint 时间点目录

- 修改人/Agent：主控 Agent
- 涉及文件：`knowledge/ops/checkpoints.md`（权威表）；`.cursor/rules/checkpoints.mdc`
- 版本变化：无（无生产代码改动）
- 修改内容：把 08-28 融合 IC 接线、两套 IC 对照、选股/买卖分层、待盯项收进**同一张时间点表**。以后同类事项只往这张表最上追加，不再另开清单。
- 原因/依据：用户要求 Excel 式 checkpoint，避免时间久了把 IC / 选股 / 买卖搞混
- 验证：表内 08-28 行与当日 CHANGELOG / 知识卡对齐
- 部署：交易端无需再改

---

## 2026-08-28 口径：选股模型 vs 买卖模型必须分开讲

- 修改人/Agent：主控 Agent
- 涉及文件：知识库 `knowledge/strategies/selection_vs_execution.md`（无生产代码改动）
- 版本变化：无
- 修改内容：书面定调 —— **选股模型在服务器**（名单和排名）；**买卖模型在 QMT/通达信**（P2/仓位/卖出）。改选股不用改交易端。08-28 已部署到交易端的是买卖模型里的 **IC 记账**（买入打分、卖出写 jsonl），不是改选股、也不是改 P2/卖出规则。
- 原因/依据：用户要求分层讲清楚，避免把「选股问题」和「买卖问题」混在一起
- 验证：文档回写 INDEX / decisions / AGENTS.md / buy_sell_rules.md / 全局 inbox
- 部署：交易端无需再改；策略重启即可加载此前已复制的记账代码

---

## 2026-08-28 Track A 三端买入打融合分 + 平仓写入 IC 样本

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`
  - `server/export_qmt_scores.py`（candidates.json 附加 `fusion_scores`，**不改顺序**）
  - `scripts/run_feedback_loop.py` / `fusion_scorer.py` / `scripts/backfill_fusion_closed_trades.py`
- 版本变化：无（不改选股/卖出判定，只给 IC 反馈记账）
- 修改内容：
  1. 买入时把三路融合分写入 `pos_state.fusion_scores`（优先读 candidates.json 的 `fusion_scores`，否则用候选池 score min-max + 主力净流入 tanh）
  2. 卖出/减仓时追加 `C:/alphapilot/fusion_closed_trades.jsonl`（source=qmt_live / qmt_sim / tdx_sim，含 pnl + `_fusion_scores`）
  3. 16:15 `update_ic_weights` 合并该 jsonl；空 `{}` 融合分不再计入 IC
  4. 历史账本回填：通达信已平仓且能对上当日 picks 的 4 笔
- 原因/依据：IC 动态权重不能再只吃服务器模拟盘 7 笔空分；要接 QMT 实盘/QMT 模拟/通达信模拟真实平仓
- 验证：三端 QMT/TDX 文件 ASCII + ast.parse 通过；py_compile 通过；backfill tdx 4 笔
- 部署：**需要**。三端策略复制到 QMT 实盘 / QMT 模拟 / TDX 模拟；`export_qmt_scores.py` 覆盖服务器；`run_feedback_loop.py` + `fusion_scorer.py` + `data/fusion_closed_trades.jsonl` 放到服务器。下一交易日买入开始带分，卖出后 16:15 才学到

---

## 2026-08-28 09:35 scanner 双路径文档固化（知识库 + 规则 + 框架页）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `knowledge/strategies/0935_momentum_scanner.md`（新增，生产规则权威）
  - `.cursor/rules/live-momentum-scanner.mdc`（新增，Agent 硬性约束）
  - `production_strategies/docs/DUAL_TRACK_BRIEFING.md`（§1.4 / §3.1a 双路径）
  - `production_strategies/docs/AGENT_RULES.md`（服务器 live_momentum_scanner 说明）
  - `AlphaPilot_Framework_CN.html`（框架页 09:35 双路径表述）
  - `knowledge/INDEX.md`、`knowledge/decisions/index.md`、`AGENTS.md`
  - `live_momentum_scanner.py`（同日已恢复 Top1000 并部署服务器）
- 版本变化：无（QMT 策略未改）
- 修改内容：固化 8/25 定案——N≥100 池内重排；N&lt;100 Top1000 资金轨；弱市仍启用。作废 8/28 误改「只在 N 内重排」结论卡。
- 原因/依据：用户要求写入知识库/规则/框架页，避免 Agent 再次改歪。
- 验证：文档审阅；框架页 HTML 结构未破坏
- 部署：框架页需同步服务器 `AlphaPilot_Framework_CN.html`（api `/api/v1/cn/framework`）

---

## 2026-08-27 启动日志显示持仓 buy_date / hold / peel

- 修改人/Agent：主控 Agent（Cursor）
- 涉及文件：Track A/B QMT sim+live、Track A/B TDX sim（4+2 文件）
- 版本变化：无（仅日志）
- 修改内容：`init`/`main` 在 sync 后调用 `_log_positions("INIT")`，逐行打印 code、shares、bd=YYYY-MM-DD、hold=N、peel=N、ext
- 原因/依据：用户反馈开机只显示 universe/holdings 数量，看不到买入日期
- 验证：QMT ASCII + ast.parse；TDX py_compile
- 部署：需重新部署对应 .py

---

- 修改人/Agent：主控 Agent（Cursor）
- 涉及文件：
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py` v2.22→**v2.23**
  - `track_a/TrackA_track_a_qmt_full_chain_live.py` v2.22-tpl→**v2.23-tpl**
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py` v2.21→**v2.22**
  - `track_b/TrackB_track_b_qmt_auction_sim.py` v2.2→**v2.3**（本会话早些时候）
  - `track_b/TrackB_track_b_qmt_auction_live.py` v2.2-tpl→**v2.3-tpl**
  - `track_b/TrackB_track_b_tdx_auction_sim.py` v1.13→**v1.14**
  - `ptrade/TrackA_track_a_ptrade_sim.py` v1.1→**v1.2**
  - `ptrade/TrackA_track_a_ptrade_live.py` v1.1-tpl→**v1.2-tpl**
- 版本变化：卖出侧逻辑 +0.1（QMT/Ptrade/TDX 对齐）
- 修改内容：全部策略统一自动读写 pos_state JSON（用户无需手改）：
  - Track A QMT：`sim_pos_state.json` / live `{ACCOUNT_TAG}_pos_state.json`
  - Track A TDX：`tdx_pos_state.json`
  - Track B QMT：`b_pos_state.json`（已有）
  - Track B TDX：`b_tdx_pos_state.json`
  - Ptrade：`ptrade_tracka_pos_state.json` / live `{TAG}_pos_state.json`
  - 持久化字段：buy_date、peak、peel_count、t2_extended、vwap_broken、wy_bc_armed、trail_armed、awaiting_new_high、peel_peak_snapshot、cost/buy_price
- 原因/依据：用户每日关 QMT/TDX 再开，重启丢失 peel/T+3 状态；Track B v2.3 已验证方案，推广至全端
- 验证：QMT 四文件 ASCII+ast.parse；TDX/Ptrade py_compile 通过
- 部署：**需要**重新部署各端对应 .py；pos_state 文件首次运行自动生成，无需手动创建

---

## 2026-08-27 Track B QMT 持仓状态持久化（v2.3）

- 修改人/Agent：主控 Agent（Cursor）
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py` v2.2→**v2.3**
  - `track_b/TrackB_track_b_qmt_auction_live.py` v2.2-tpl→**v2.3-tpl**
- 版本变化：v2.2 → v2.3（卖出侧逻辑相关）
- 修改内容：
  - 新增 `C:/alphapilot/b_pos_state.json` 持久化：`buy_date`、`peak`、`peel_count`、`t2_extended`、`vwap_broken`、`wy_bc_armed`、`trail_armed`、`awaiting_new_high`、`peel_peak_snapshot`、`buy_price`
  - `init` 加载 pos state；`_sync_holdings` 合并恢复；买入/卖出/减仓/每轮 `_check_sell` 后保存
  - `_recover_buy_date` 优先读 pos state，再读 trade log
- 原因/依据：用户每日关闭 QMT 再开盘，重启后 `[SYNC] +` 重建持仓丢失内存状态（300191：`buy_date` 空 → `hold_days=999` 导致 T+3 上限失效；`peel_count` 归零重复减仓）
- 验证：两文件 ASCII + ast.parse 通过
- 部署：**需要**复制 sim 到 QMT 模拟 python 目录；live 模板按需复制。首次部署后若 300191 仍无 `buy_date`，可手动在 `b_pos_state.json` 写入 `"buy_date": "20260820"` 或补一条 BUY 到 `b_trades_fullchain.json`


## 2026-08-19 VWAP 数据源优化：优先用 QMT 原生分时均价（get_full_tick），5m K线仅兜底

- 修改人/Agent：主控 Agent（用户质疑：QMT 自己有数据，为何算出来的 VWAP 差 100 倍，是计算错还是抓取错）
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py` / `track_b/TrackB_track_b_qmt_auction_live.py`
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py` / `track_a/TrackA_track_a_qmt_full_chain_live.py`
  - 测试：`track_b/_test_day_vwap_qmt.py`（新增）
- 版本变化：无版本号变化（QMT 四版 `_day_vwap` 函数内部改动）
- 修改内容：**结论：是计算错，不是抓取错。** QMT 5m K线本身完全正确，错误在旧代码把"成交额(元) ÷ 成交量(手)"直接相除——手是 100 股，所以结果天然放大 100 倍（300591 实测 vwap=806.98，股价 ~8.07）。为彻底消除这类单位换算风险，`_day_vwap` 改为两级数据源：
  1. **主路径（QMT 原生）**：`C.get_full_tick([code])` 的当日累计 `amount`（元）/`pvolume`（股）即权威分时均价，零单位换算；并用合理性护栏 `0.5×lastPrice ≤ VWAP ≤ 2×lastPrice` 兜底，任何残留单位错配（如 100x）都会被拒并落回 5m。
  2. **兜底路径（5m K线）**：保留 `amount / (volume×100)`（手→股），与主路径结果一致。
- 原因/依据：QMT 策略环境 `ContextInfo.get_full_tick` 官方可用（不能用于回测，仅实时；策略本身就是实时运行）。当日累计 amount/pvolume 就是 QMT 分时图上的"均价"黄线，最权威、最不容易出单位错。
- 验证：6 文件 `py_compile` 全通过；`_test_day_vwap_qmt.py` 4/4 PASS（tick 主路径 8.13、100x 错配被护栏拒绝回退 5m、无 get_full_tick 环境回退 5m、amount=0 回退 5m）；v1.6 动态强平线 9/9 + 其余 4 组回归（v1.4/v1.5/v2.15/v2.16）全 PASS。
- 部署：**需用户手动部署**到 QMT 模拟盘/实盘模板，次日 09:25 起生效；TDX 两版不改（已用快照 Average 字段）。

---

- 修改人/Agent：主控 Agent（用户要求：振幅大的票不应亏 8 个点就被 t2_force 强平，规则应动态化，且以后不能再现类似情况）
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（v1.5→v1.6）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（v1.5-tpl→v1.6-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（v1.5→v1.6）
  - `track_a/TrackA_track_a_qmt_full_chain_sim.py`（v2.16→v2.17）
  - `track_a/TrackA_track_a_qmt_full_chain_live.py`（v2.16-tpl→v2.17-tpl）
  - `track_a/TrackA_track_a_tdx_full_chain_sim.py`（v2.14→v2.15）
  - 测试：`track_b/_test_sell_dynamic_v16.py`（新增）
- 版本变化：见上（卖出逻辑 + 买入逻辑同时改）
- 修改内容：
  1. **`_day_vwap` 单位修复（QMT 两版）**：QMT 5m 行情的 `volume` 是"手"（100 股），`amount` 是元。
     原 `amount/volume` 直接相除会把 VWAP 放大 100 倍（实测 300591 出现 vwap=806.98，实际股价约 8.07），
     导致 `price < vw` 恒真 → `vwap_broken` 恒置位 → 盈利票 301130 在 14:45 被 `t2_force_after_extend` 误杀（+33% 也被卖）。
     修复：`tv += volume * 100.0`，VWAP 恢复真实元/股。（TDX 两版走快照 `Average` 字段或 close*volume 同单位近似，无此 bug，不改）
  2. **卖出端动态强平线（`_t2_force_floor` + `_day_amplitude_pct`，6 文件）**：
     原来 14:45 `t2_force` 固定 `ret < 0` 就强平。改为 `ret < force_floor` 才强平：
     `floor = -(max(0, 当日振幅% - 4%) * 0.5 + 超额年化波动率 * 0.10)`，并设 `T2_FORCE_FLOOR_MAX=-10%` 兜底；
     `hard_stop`（自适应 hs）仍先于强平线生效，接管真正的尾部风险。宽振幅/高波动票的正常回撤在当日区间内可持有到 T+3。
  3. **买入端滑点保护（`MAX_BUY_SLIP_PCT=0.02`，6 文件）**：P2 触发价是 5m 收盘价，快涨时市价单成交价远超触发价
     （300591 08-18：触发 7.88 实际成交 8.54，+8.4%）。虚高成本把次日 -1% 的正常回撤变成 -8.7% 深亏，被旧固定 0% 强平线误杀。
     现在 `_get_last / _last_price` 实时价 > 触发价×(1+2%) 时**不追买**，候选留待下一根 bar。
- 原因/依据：
  - 2026-08-19 万里马（300591）：08-18 P2 触发 7.88 成交 8.54（+8.4% 滑点），08-19 当日实际仅 -1%（收 7.80，相对昨收 -7.02%），
    但相对虚高成本 -8.7%，旧 `t2_force -8.7%` 在 14:45 强平。
  - 2026-08-19 西点药业（301130）：`_day_vwap` 100x 单位 bug → `vwap_broken` 恒真 → 盈利 +33% 仍被 `t2_force_after_extend` 强平。
  - 用户结论：规则应动态化，宽振幅票的正常回撤不应在 8% 处被一刀切强平。
- 验证：
  - 6 个策略文件 `python -m py_compile` 全部通过；
  - `_test_sell_dynamic_v16.py` 9/9 PASS（宽振幅 -8.7% 回撤不再强平并转 T+3 延长；低振幅 -8.7% 仍强平；振幅 29.7%→floor 封顶 -10%；
    另含 300591 08-19 真实数据两用例：公平成本 7.88 次日 -1.0% 在 6.9% 振幅日被持有、虚高成本 8.54 的 -8.7% 仍强平以证明滑点保护的必要性）；
  - 回归：`_test_sell_rotation_v14` 10/10、`_test_rotation_v15` 9/9、`_test_sell_rotation_v215` 11/11、`_test_rotation_v216` 9/9 全部 PASS。
- 部署：**需用户手动部署**到 QMT 模拟盘/实盘模板/TDX `PYPlugins\user`，次日 09:25 起生效；新增注释均为 ASCII。

---

- 修改人/Agent：主控 Agent（用户要求「下跌通道不买」在三端对齐：网页 A1 决策层 / QMT / 通达信）
- 涉及文件：
  - `money_flow_gate.py`（服务器共享资金门）——新增 `_bare6` / `_is_abr_plausible` / `_is_chg_plausible`；
    `apply_money_flow_gate` 新增 `min_change_pct` 参数；quotes 匹配统一裸 6 位代码；abr/chg 垃圾值防御
  - `morning_live_fund_select.py`（09:35 A1 终选）——调用资金门时传 `min_change_pct=0.0`（当日非上涨硬门）
  - `api_server.py` / `_srv_api_server.py` / `_server_api_server.py`（A1 决策层 2 处）——同步传 `min_change_pct=0.0`
  - `live_momentum_scanner.py`（09:35 全市场重排数据源）——THS/akshare 表头漂移时 chg/abr 越界值置中性
  - `server/export_qmt_scores.py`（fullpool_live 导出）——导出前 abr/chg 合理性校验，垃圾值强制 fail
- 版本变化：无（服务器逻辑文件，非交易端加密文件）
- 修改内容：
  1. **symbol 归一化**：`get_quotes_batch`（腾讯）要求裸 6 位代码，带 `.SZ` 后缀匹配失败返回空，
     资金门会回退到 rec 自带字段（可能是 THS 表头漂移的垃圾值）。`_bare6` 统一处理
     `002437.SZ / sz002437 / SH600519 → 002437 / 600519`。
  2. **当日非下跌硬门**：`apply_money_flow_gate` 新增 `min_change_pct` 参数。A1 决策层（09:35 终选 +
     网页 A1 两处）传 `0.0`：当日 `chg < 0` → 资金门 fail，与客户端 P2 `c >= prev_close` 同口径对齐。
  3. **垃圾值防御**：abr 须∈[0,1]、chg 须∈[-30,30]，越界视为数据错误（`data_error` 标记）并强制
     `money_flow_pass=False`；`live_momentum_scanner` 源头把越界值置中性（chg→0、abr→0.5），
     `export_fullpool_live` 导出前兜底校验。
- 原因/依据：2026-08-19 誉衡药业（002437）当日跳水仍出现在「决策层 A1_permission」买入指令中。
  根因：① 002437 在 09:35:45 决策时点确实红盘（+2.31%），当日非下跌本来就拦不住；② 服务器
  `fullpool_live.json` 中 `change_pct=273.0`、`active_buy_ratio=22298681`（THS 表头漂移/东财字段误读），
  垃圾值让它以「资金门通过 + 全池最强」假象排进 Top1；③ 客户端 QMT/TDX P2 有 `c>=prev_close` 兜底
  故未成交（实际买入 000651/300139 等），但网页 A1 指令误导人工跟单、污染 Track B 排序。
- 验证：
  - 7 个修改文件 `ast.parse` 语法全部通过；
  - `_bare6` 5 种 symbol 格式全部归一化正确；
  - 用 20260819.fullpool_live.json 真实数据跑合理性校验：39 只中 14 只垃圾值强制 fail，
    `money_flow_pass=True` 从 16 降到 2，002437.SZ 正确 fail 且带 `data_error`；
  - 客户端 QMT/TDX 6 文件核查：P2 当日非下跌 guard 均已存在（08-18 已同步），无需再改。
- 部署：
  - 服务器 `/home/ubuntu/alphapilot/`：覆盖 `money_flow_gate.py`、`morning_live_fund_select.py`、
    `api_server.py`、`live_momentum_scanner.py`、`production_strategies/server/export_qmt_scores.py`，
    重启 api_server / 次日 cron 生效。
  - 交易端 QMT/TDX：无需修改（P2 guard 已就位）。

## 2026-08-19 轨道B竞价阶段接入形态突破加分 + 形态加分权重提升

- 修改人/Agent：主控 Agent（用户要求"形态加分同步进轨道B竞价阶段 + 形态加分要多一些"）
- 涉及文件：
  - `server/export_qmt_scores.py` —— `export_fullpool()` 新增 `score`/`pattern_breakout`/`pattern_breakout_delta` 字段
  - `track_b/TrackB_track_b_qmt_auction_sim.py` / `track_b/TrackB_track_b_qmt_auction_live.py` / `track_b/TrackB_track_b_tdx_auction_sim.py` —— `_load_fullpool_classic` 归一化 `score`；`_p1_gate` 基础分优先取 `score`（含形态加分），缺失回退 `score_0500`
  - `pattern_breakout_boost.py`（根目录，服务器部署源）—— `PATTERN_BOOST_FULL` 0.06→0.15，`PATTERN_BOOST_CORE` 0.03→0.08
- 版本变化：TrackB 三版 v1.x → v1.x（逻辑微调，升一位小版本：sim v1.1→v1.2、live v1.2-tpl→v1.3-tpl、tdx v1.2→v1.3）
- 修改内容：
  1. **服务器 `export_fullpool`（06:30 cron）**：每行新增 `score`（A 臂最终分，含形态突破/趋势/草木皆兵等软加分）、`pattern_breakout`、`pattern_breakout_delta`。`score_0500` 保留裸模型分做参考。
  2. **TrackB 三版 `_load_fullpool_classic`**：加载 fullpool 后把每行 `score` 归一化为 `score`（服务端最终分，含加分），缺失时回退 `score_0500`。
  3. **TrackB 三版 `_p1_gate`（09:25-09:35 竞价）**：`base = it.get("score") if not None else score_0500`，使形态加分影响竞价排序（原只用裸 `score_0500`）。
  4. **`pattern_breakout_boost.py`**：加分默认值 FULL 0.06→0.15、CORE 0.03→0.08。
- 原因/依据：
  - 用户指出：现有选股多为"前一天大涨"的股票，T+0 追入第二天方向不确定（约 1/3 概率向上）；而"大阳线→4-5 天横盘→再拉升"形态是回调充分后的再次启动点，成功率更高，加分应更多。
  - 21,697 历史样本量化：FULL 形态票（形态4核心+大盘+行业全中）5日最大涨幅≥3% 成功率 **78.4%**、≥7% 达 **53.2%**；CORE3（核心≥3条）≥3% 达 64.4%；全形态票基准 ≥7% 仅 25.5%。普通追高次日向上约 1/3。
  - 原加分 0.06 经 09:35 重排（×0.6）稀释后仅约 0.04 个 z-score std，对排序几乎无影响；0.15 对应约 0.09-0.15 std，才能让形态票进入有效排序竞争。
- 验证：5 文件语法校验通过；服务器 `export --fullpool` 实际运行 OK（99 只全部带 `score` 字段）；dry-run 加分逻辑正常（今日 99 只池无形态命中为旧代码预期，明日 05:00 新逻辑生效）；TrackB 三版新增注释均为 ASCII（原文件历史中文不动）。
- 部署：**服务器已部署**（`pattern_breakout_boost.py` + `export_qmt_scores.py` 已 scp 覆盖，已验证）；**TrackB 三版需用户手动部署**到 QMT 模拟盘/实盘模板/TDX `PYPlugins\user`。本地 `C:\alphapilot\scores\` 今日 fullpool.json 已含 `score` 字段（服务器重跑生成）。

---

## 2026-08-19 Track A 文件命名对齐 Track B 规范（模拟/实盘/账号一眼可辨）

- 修改人/Agent：主控 Agent（用户指出轨道 A 命名导致模拟/实盘/账号对不上）
- 涉及文件：`track_a/` 3 个策略文件重命名 + 内部标识；`track_b/` 3 个文件注释引用；`_test_rotation_v216.py`/`_test_sell_rotation_v215.py` 路径；`README.md`/`docs/AGENT_RULES.md`/`docs/TRACK_A_B_SELECTION_COMPARISON.md`/`track_a/BT_ABR_GATE_REPORT.md`；`knowledge/decisions/index.md`
- 版本变化：无逻辑变化（纯重命名 + 标识）
- 修改内容：
  1. **文件重命名**（对齐 Track B 的 `TrackX_track_x_<平台>_<策略>_<环境>.py` 规范）：
     - `TrackA_qmt_model_full_chain_v2.py` → `TrackA_track_a_qmt_full_chain_sim.py`（QMT 模拟盘）
     - `TrackA_qmt_model_full_chain_template.py` → `TrackA_track_a_qmt_full_chain_live.py`（QMT 实盘模板）
     - `TrackA_tdx_full_chain.py` → `TrackA_track_a_tdx_full_chain_sim.py`（TDX 模拟盘）
  2. **INIT 日志加 `track-A` 前缀**（与 Track B 的 `track-B` 对齐，QMT/TDX 端一眼区分轨道）：
     - QMT 模拟：`[INIT] track-A qmt-sim v2.16 ...`
     - QMT 实盘：`[INIT] track-A qmt-live v2.16-tpl ...`
     - TDX 模拟：`[INIT] track-A tdx-sim v2.14 ...`
  3. 头部注释标注新文件名；TDX 运行命令 `python TrackA_track_a_tdx_full_chain_sim.py`
- 原因/依据：用户 2026-08-19 反馈"轨道 A 命名模拟/实盘/账号对不上"，要求按 Track B 一样命名。旧命名无 `track_a`、无统一 sim/live 后缀、`v2`/`template` 不直观，且 INIT 日志无轨道前缀。
- 验证：3 文件 `py_compile` 通过；QMT 2 文件纯 ASCII（non-ascii=0）；全库 `rg TrackA_qmt_model_full_chain|TrackA_tdx_full_chain` 仅剩 CHANGELOG 历史条目与 knowledge 历史决策行（历史快照保留不改）；单测 v2.16/v2.15 跑通。
- 部署：**需用户手动部署**。QMT 模拟盘/实盘模板/TDX 各替换交易端为新命名文件；重部署后日志出现 `[INIT] track-A ...` 即确认对应关系。账号对应：QMT 模拟 98009473、QMT 实盘 8886269286、TDX 模拟 1190388433。
- 备注：`ACCOUNT_TAG` 未动（Track A 模拟日志前缀 `sim_`、实盘 `live`，与 Track B 的 `b`/`b_live` 已区分），避免破坏既有日志文件。

---

## 2026-08-18 资金流数据源修复 + CapitalPulse 实时板块资金流接入

- 修改人/Agent：主控 Agent（修复东财字段误读审计出的 Bug 1 + 接入网页端 CapitalPulse）
- 涉及文件：
  - `live_fund_flow.py`（根目录，服务器部署源）—— **东财字段误读核心修复**
  - `production_strategies/server/export_qmt_scores.py`—— fullpool_live 导出补全分层资金流/多日累计/资金排名
  - `morning_live_fund_select.py`—— `_merge_ths_into_items` 透传分层资金流（live_super_large/large/mid/small_net）
  - `live_momentum_scanner.py`—— 09:35 评分加入 CapitalPulse 板块实时主力净额 z 加成（`W_SECTOR_FLOW`，默认 0.10，环境变量可调）
  - `track_b/TrackB_track_b_qmt_auction_sim.py` / `TrackB_track_b_qmt_auction_live.py` / `TrackB_track_b_tdx_auction_sim.py`—— `_live_pool_survivors` 映射新字段；live P2 加"散户接盘/主力深流出"软降级（排序罚分，非硬否决）
- 版本变化：轨道 B 3 文件客户端逻辑微调（无版本号提升）；资金流链路数据源修复
- 修改内容：
  1. **live_fund_flow.py（核心修复）**：旧实现把东财 `f184`(主力净占比%)/`f185` 误当"大单/超大单净额"叠加进 `main_net`，并把 `f84`(小单净额,元) 当"主动买占比"（实测 000001 出现 `main_net=2`、`abr=19405918198` 垃圾值）。改为与 CapitalPulse 已验证一致的字段语义：
     `f62=主力净额` `f66=超大单` `f72=大单` `f78=中单` `f84=小单` `f124=时间戳`；
     改用 `ulist.np/get` 批量接口（50只/请求）+ push2delay 回退 + `fltt=2/invt=2/np=1/ut token`；
     **不再伪造 `active_buy_ratio`**，下游 `live_abr` 自动回退腾讯外盘/内盘口径。
  2. **export_qmt_scores.py（fullpool_live）**：新增导出 `super_large_net/large_net/mid_net/small_net`（live_* 优先，否则 Wind 分档 `wind_inst/large/mid/retail_net`）、`main_net_3d/10d`、`fund_pos_days_5`、`fund_soft_bonus`、`fund_hard_fail`、`money_phase`，并新增全池 `fund_rank`（main_net 百分位 0~100）。
  3. **live_momentum_scanner.py**：新增 `load_capitalpulse_sector_flow()`（读 `data/sector_flow_realtime.sqlite3`，CapitalPulse 每 3 秒全量采集 30 个申万二级行业实时主力净额）与 `sector_flow_z_by_stock()`（按个股 `industry_l2` 名称映射板块，截面 z），09:35 融合分 = pipeline_z×0.6 + 动量z×0.4 + 板块资金z×0.1。数据缺失时中性 0 不阻断。
  4. **轨道 B 客户端**：`_live_pool_survivors` 映射 main_net/3d/10d/分层/fund_rank/money_phase；live P2 中若 `main_net < -3e7` 或"主力流出+散户明显接盘"则打 `live_main_out/live_retail_chase` 标记，排序时排到同档正常票之后（不否决）。
- 原因/依据：2026-08-18 资金流审计（Bug 1 + 4 个数据完整性缺口）；用户要求修复所有问题数据源，并确认网页端 CapitalPulse 提供**已验证正确的**东财字段语义与 3 秒级板块实时资金流。
- 验证：`py_compile` 7 文件全部通过；`live_fund_flow` 实测 5 只返回合理分层净额（自洽：main=超大+大）；板块读取实测 30 板块 / 2627 只个股命中 z；Track B v1.5 / Track A v2.16 / v2.15 单测 29/29 通过（无回归）。
- 部署：**需用户手动部署**。服务器：`live_fund_flow.py`、`live_momentum_scanner.py`、`morning_live_fund_select.py` 覆盖 `/home/ubuntu/alphapilot/`；`production_strategies/server/export_qmt_scores.py` 覆盖 `/home/ubuntu/alphapilot/export_qmt_scores.py`；轨道 B 3 份策略文件替换 QMT/TDX 加密版本。下一交易日生效。
- 备注：CapitalPulse 个股资金流为"按需订阅"（WebSocket 客户端触发），服务器 09:35 链已改走 `live_fund_flow` 批量拉取（修复后字段正确）；板块级 3 秒实时流由 run_server 内 collector 常驻采集。`W_SECTOR_FLOW` 默认 0.10，可按观察调优。

---

## 2026-08-18 轮动加固 v2.16 / v2.14 / v1.5：T+1 免疫 + 每日轮出上限 + 迟滞弱信号门（6 文件）

- 修改人/Agent：主控 Agent（落地 DSH 卖出端评审 3 处真坑）
- 涉及文件：
  - `track_a/TrackA_qmt_model_full_chain_v2.py`（Track A QMT 模拟盘 v2.15 → v2.16）
  - `track_a/TrackA_qmt_model_full_chain_template.py`（Track A QMT 实盘模板 v2.15-tpl → v2.16-tpl）
  - `track_a/TrackA_tdx_full_chain.py`（Track A TDX 模拟盘 v2.13 → v2.14）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（Track B QMT 模拟盘 v1.4 → v1.5）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（Track B QMT 实盘模板 v1.4-tpl → v1.5-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（Track B TDX 模拟盘 v1.4 → v1.5）
  - 新增单测：`track_a/_test_rotation_v216.py`、`track_b/_test_rotation_v15.py`
- 版本变化：6 文件逻辑版本 +1（轮动逻辑加固）
- 修改内容（DSH 评审"三处真坑"逐一落地）：
  1. **T+1 免疫**：`ROTATION_MIN_HOLD_DAYS 1 → 2`，仅 T+2 及以上持仓可被轮出，
     T+0/T+1 免疫（哪怕是最弱持仓）——与被废除的 T+2 强平无缝衔接。
  2. **每日轮出上限**：新增 `ROTATION_DAILY_MAX=1`，`_rotation_sell` 用
     `__ROT__` 伪代码日级锁（复用 order_locks 文件）限制每天最多轮出 1 只，
     轮出成功后即打锁，同日再次触发直接跳过。
  3. **迟滞弱信号门**：新增 `ROTATION_WEAK_GATE=True`。仅当最弱可轮持仓出现
     **具体弱信号**（当日下跌 / 跌破日VWAP / 早退信号 / 浮亏）才轮出；
     若最弱持仓仍健康（红盘、在 VWAP 上方、无信号）则不轮、跳过本次买入，
     不为噪声边界换仓。
     - 设计说明：初版用 `ROTATION_MIN_WEAK_SCORE=0.55` 绝对阈值，但弱度评分是
       池内排名归一化，并列/数据缺失时 rank 分量塌缩（离线单测验证最弱票仅
       得 0.45），无法区分"相对最弱但健康"与"真正走弱"，故弃用绝对阈值，
       改为池无关的绝对信号门。
- 原因/依据：DSH 卖出端评审（2026-08-18）：T+0/T+1 新票信息少、波动大，易被
  误判为弱而次日被轮出；每日最多轮出 1 只限制换手=限制决策错误率；新候选需
  margin 才换仓、防噪音边界反复换仓白交手续费（P2 为二元判定暂无候选连续分，
  故用"最弱持仓必须确有弱信号"作为保守代理）。
- 验证：
  - 6 文件 `ast.parse` 全部通过；QMT 4 份纯 ASCII（non-ascii=0）；
  - 新常量/`__ROT__` 锁符号 6 文件齐全，无 `ROTATION_MIN_WEAK_SCORE` 残留；
  - 单测 39/39 通过：TA v2.15 回归 11/11、TB v1.4 回归 10/10、
    TA v2.16 9/9（T+1 免疫 / 迟滞门 / 每日上限）、TB v1.5 9/9（同上）。
- 部署：**需用户手动部署**。QMT 模拟盘/实盘模板/TDX 各 6 处替换新版加密文件，
  下一交易日生效。部署后观察日志：`[ROT] skip: weakest ... still healthy` /
  `[ROT] daily cap 1 reached` 是否符合预期。
- 备注：DSH 评审其余建议（相对强度评分、14:45 瀑布重构、T+4 影子持仓）本次
  未动——相对强度需客户端新拉指数/板块数据，瀑布重构与现"买入驱动"轮动理念
  冲突，均留待影子数据支撑后再评估。

## 2026-08-18 卖出端改造（v2.15 / v2.13 / v1.4）同步到其余 5 个生产策略文件

- 修改人/Agent：主控 Agent（延续 DHS 卖出端评估 P0+P1 落地）
- 涉及文件：
  - `track_a/TrackA_qmt_model_full_chain_template.py`（Track A QMT 实盘模板 v2.14-tpl → v2.15-tpl）
  - `track_a/TrackA_tdx_full_chain.py`（Track A TDX 模拟盘 v2.12 → v2.13）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（Track B QMT 模拟盘 v1.2 → v1.4）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（Track B QMT 实盘模板 v1.3-tpl → v1.4-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（Track B TDX 模拟盘 v1.3 → v1.4）
  - 新增 `track_b/_test_sell_rotation_v14.py`（Track B 卖出端单测）
- 版本变化：5 文件逻辑版本 +1（与 Track A QMT 模拟盘 v2.15 对齐）
- 修改内容（每文件按 QMT/TDX 各自签名适配，逻辑与 v2.15 一致）：
  1. **T+2 条件化强平**：`ret < T2_EXTEND_PROFIT_MIN(0)` 强卖；盈利且无早退信号
     延长至 `T2_EXTEND_MAX_DAYS=3`（T+3）；已延长 / `wy_bc_armed` / `vwap_broken` /
     硬止损 → 卖出；peel 保持兜底。替换原 `price >= cost*0.95` 一刀切。
  2. **动态强弱轮动（P1）**：持仓满 `MAX_HOLDINGS` 且候选 P2 通过后，先轮动卖
     最弱 1 只再买入（A股 T+0 回转）。Track B 三版在 `_p2_decide` 通过后触发
     （循环内）；Track A TDX 在 `_check_buy` 开头先探测候选是否 P2 通过再轮动。
  3. **弱度评分 + 动量保护**：`ret30% + vwap20% + day20% + early15% + peel10% +
     days5%`，相对排名归一化，当日 >3% 且量比 >1.3 跳过。
  4. 新增 `_hold_days` / `_weakness_score` / `_rotation_sell`（Track A/B TDX 另加
     `_closed_5m_bars` / `_volume_ratio_of`，复用各文件已有 `_get_volume_ratio`）。
  5. Track B QMT 两版：轮动卖出后重查资金 `m_dAvailable`；TDX 两版重查 `_query_cash()`。
  6. 顺带清理各文件残留的非 ASCII 中文注释（西点药业 301130 / 放量上涨），
     QMT 4 份文件全部纯 ASCII。
- 原因/依据：用户要求把 Track A QMT 模拟盘已验证的 v2.15 卖出端改造同步到
  其余 5 个策略文件（Track A/B × QMT sim/live + TDX sim），保持六端逻辑一致。
- 验证：
  - 6 文件 `ast.parse` 语法全部通过；
  - QMT 4 份 `non-ascii = 0`（加密安全）；
  - 符号一致性：6 文件均含 5 个新函数 + 8 个轮动常量，无缺失；
  - Track A 单测 `_test_sell_rotation_v215.py` 11/11 通过；
  - Track B 单测 `_test_sell_rotation_v14.py` 10/10 通过
    （_hold_days 日期格式 / 盈利延长 / 亏损强卖 / 弱度评分选最弱）。
- 部署：**需用户手动部署**。Track A 实盘模板 → QMT 实盘各账号；Track A TDX →
  TDX 模拟盘；Track B QMT 模拟盘 / 实盘模板 / TDX 模拟盘。下一交易日生效。
- 备注：本次同时核实了 2026-08-18「5 点管线未生成是否导致选股模型不触发」，
  结论见对话记录——管线 05:00 崩溃（VM2.5 1200s 超时）但 09:21 重跑补出全部
  文件，客户端每 bar 轮询自动恢复触发，当天 Track A 09:50 买 002396.SZ、
  Track B 09:45 买 300591.SZ，**选股模型未被永久关闭**。

## 2026-08-18 Track A QMT 模拟盘卖出端改造：T+2 条件化 + 动态强弱轮动（v2.14 → v2.15）

- 修改人/Agent：主控 Agent（落地 DeepSeek Harness 卖出端评估 P0+P1）
- 涉及文件：`track_a/TrackA_qmt_model_full_chain_v2.py`（QMT 模拟盘）
  - 新增 `_test_sell_rotation_v215.py`（卖出端改造离线单测）
- 版本变化：v2.14 → v2.15（逻辑改动）
- 修改内容（对应 DHS 补丁 A/B/C/D 部分，全部修正后落地）：
  1. **T+2 强平条件化**（替换原 `price>=cost*0.95` 一刀切延期）：
     - `ret < 0` → 强卖（数据支持：亏损组多拿期望为负）；
     - 盈利但无早退信号 → 延长，上限 `T2_EXTEND_MAX_DAYS=3`（T+3）；
     - 已延长 / 触发早退信号 / 硬止损 → 卖出；peel 在延长期间保持启用兜底。
  2. **动态强弱轮动（P1）**：持仓满 `MAX_HOLDINGS` 且候选有 P2 通过时，
     先评估候选（P2 前置，不为弱票卖旧仓），再卖最弱 1 只腾位，当根 bar
     重新查资金买入（A股 T+0 回转）。
  3. **弱度评分**：`ret30% + 破VWAP20% + 当日20% + 早退15% + peel10% + 距T+2 5%`，
     相对排名归一化，动量保护（当日 >3% 且量比 >1.3 → 跳过）。
  4. 新增 `_hold_days` / `_closed_5m_bars` / `_volume_ratio_of` /
     `_weakness_score` / `_rotation_sell` 五个函数。
- 修正的 DHS 补丁 bug（共 2 处）：
  1. **`_hold_days` 日期格式 bug**：DHS 用 `%Y-%m-%d` 解析 `buy_date`，但
     v2.14 存 `%Y%m%d` → 必然 ValueError → 返回 999 → 轮动永无可卖持仓。
     已统一为 `%Y%m%d`（兼容 `YYYY-MM-DD`）。
  2. **`_rank01` 排序 bug**：DHS 用 `enumerate(vals)`（原始顺序）而非
     `enumerate(sorted(vals))`，有重复值时 rank 错乱，会把强票误判为最弱。
     已改为枚举排序后位置。
  - 另：`_weakness_score` 按 DHS 建议重构为 `_weakness_score(C, today)`
    单一签名；`_volume_ratio_of` 移植 Track B v1.1 同时段量比（比 DHS 日线近似更准）。
- 原因/依据：用户观察到"T+2 卖出后 T+3 才涨"；DSH 评估（2026-08-16）确认
  "盈多拿、亏早走"方向，但盈利延长须 peel 兜底、轮动须防卖飞。用户选择
  P0+P1 一次落地、只改 Track A QMT 模拟盘、轮动卖出后当根 bar 买入。
- 验证：
  - 语法 `ast.parse` 通过；**纯 ASCII（0 非 ASCII 字节）**，QMT 加密安全；
  - 单测 `_test_sell_rotation_v215.py` 11/11 通过：
    盈利 T+2 延长 / 亏损 T+2 强卖 / 满仓轮动卖最弱（600002 -4%）并买入新票 /
    `_hold_days` 三种日期输入。
- 部署：**需用户手动部署**到 QMT 模拟盘（替换 `AP全链交易模拟_TRACK_A.py` 加密文件），
  下一交易日生效。先 dryrun 观察 `[EXT]`/`[ROT]`/`t2_force` 日志。
- 备注：Track A 的 QMT 实盘模板 / TDX 版、Track B 三版本**本次未同步**，
  待模拟盘验证通过后再按 DHS 补丁 E 部分同步。

## 2026-08-18 全链 P2 修复：5m 跨天脏数据 + 当日非下跌 guard + _log_trade（6 文件）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（QMT 模拟盘 v1.1 → v1.2）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（QMT 实盘模板 v1.2-tpl → v1.3-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（TDX 模拟盘 v1.2 → v1.3）
  - `track_a/TrackA_qmt_model_full_chain_v2.py`（Track A QMT 模拟盘 v2.13 → v2.14）
  - `track_a/TrackA_qmt_model_full_chain_template.py`（Track A QMT 实盘模板 v2.13-tpl → v2.14-tpl）
  - `track_a/TrackA_tdx_full_chain.py`（Track A TDX 模拟盘 v2.11 → v2.12）
- 版本变化：全部 6 文件版本号 +1（逻辑改动）
- 修改内容（三处根因，QMT/TDX 各自适配）：
  1. **`_get_m5_bars` / `_day_vwap` 跨天脏数据**（QMT 4 份全部命中）：
     `C.get_market_data_ex(count=48)` 未传 `start_time`，早盘会返回**前一日** 5m bar；
     旧代码用 `CONF_START_MIN + i*5` 反推时间、从不按日期过滤 → P2 的
     p935/VWAP/量比全部基于历史数据计算。
     - 新增 `_bar_times(df, n)` 助手：从 QMT DataFrame 索引解析真实
       `(date_str, tmin)`（兼容时间串 `20260818093500` / `2026-08-18 09:35:00`）。
     - `_get_m5_bars` / `_day_vwap` 显式传 `start_time=today` + `end_time=today`，
       且仅保留今日 bar。
  2. **P2 当日非下跌 guard**（6 文件全部）：`_p2_decide` 主 bars 路径在
     趋势判断前加 `if prev_close > 0 and c < prev_close: continue`，与
     snapshot 降级路径（`price > prev_close`）对齐，杜绝在下跌通道内
     盘中反弹时买入。
  3. **`_log_trade` 内存账本不回写**（QMT 3 份：TrackB LIVE / TrackA v2 /
     TrackA template）：`_log_trade` 落盘后未更新 `C.trade_log`，下次调用
     用旧列表覆盖文件 → 多笔成交只留最后一笔。已补 `C.trade_log = ledger`。
- 原因/依据：用户报告 2026-08-18 模拟盘 Track B 买入 `301130.SZ 西点药业`
  （rank=28、money_flow_pass=false、当日 -2.25%）「P2 当日动量的 5m 不是
  放量上涨」。取证：分钟线还原 09:30-09:40 连续下跌、日志买入价 30.6 高于
  当日最高价（实成交 29.231）、`b_trades_fullchain.json` 只留一笔（另一笔
  被 `_log_trade` 覆盖）。根因即上述跨天脏数据 + 缺当日非下跌 guard。
- 验证：
  - 全部 6 文件 `ast.parse` / `py_compile` 语法通过；
  - `_bar_times` 单测：兼容 3 种索引格式，今日过滤正确；
  - `_test_fullpool_live_sync.py`、`_test_buy_window.py` 回归不受影响。
- 部署：**需要用户手动部署**。QMT 模拟盘 / QMT 实盘模板 / TDX 模拟盘 / TDX 实盘
  6 处替换为新版本，下一交易日生效。部署后观察：Track B 不再买 rank 靠后且
  当日下跌的 fallback 股；`b_trades_fullchain.json` 多笔成交不再互相覆盖。
- 备注：TDX 版 `_get_m5_bars` 本就按真实日期过滤（已验证正确），本次仅补
  bars 路径 day-trend guard + 升版本。

## 2026-08-18 服务器 05:00 管线超时崩溃 → 09:21 补跑救援（QMT 404 根因）

- 修改人/Agent：主控 Agent（应急救援）
- 涉及文件：服务器 `/home/ubuntu/alphapilot/alphapilot_pipeline_v3.py`（非本地 production_strategies，属服务器侧）
- 版本变化：无（仅配置修复）
- 修改内容：
  1. **根因**：2026-08-18 03:06 服务器 `alphapilot_pipeline_v3.py` 被改动，VM2.5 选股步骤 `run_step` 超时从 **3600 秒被改为 1200 秒**。`recommend.py` 实际稳定需要 **2305–2350 秒（~39 分钟）**，1200 秒必然超时 → 今天 05:00 管线在 `VM2.5模型选股` 崩溃，`daily_recommend.json` 未更新（仍是 08-17 的）。
  2. **连锁影响**：06:30 `export_qmt_scores.py --fullpool` 因 `mtime != 今天` 而 SKIP；09:36 `--fullpool-live` 也依赖新鲜数据 → 全部 QMT 文件 404 → QMT 端报 `[FETCH] fullpool fail: HTTP Error 404`。
  3. **修复**：`1200 → 3600`（与 `bak_qualitygate_20260804` 备份一致），并备份为 `alphapilot_pipeline_v3.py.bak_20260818_before_timeout_fix`。
  4. **补跑**：09:21 后台重启 `alphapilot_pipeline_v3.py`（`ENABLE_SURGE_ARM_B=1 SURGE_ARM_B_MULT=0.85`），09:22 进入 VM2.5，**10:06:35 完成**（总耗时 2681s，池 141 只，Top2=思林杰/瑞凌股份）。
  5. **导出补跑**：部署救援 watcher，pipeline 完成后自动重跑 09:35/09:36 链（`live_momentum_scanner` → `morning_live_fund_select` → `export_qmt_scores.py --fullpool/--fullpool-live/默认`）。09:58–09:59 全部生成成功。
- 验证：
  - 09:59:33 nginx 全部 HTTP 200：`20260818.fullpool.json` / `fullpool_live.json` / `20260818.json` / `candidates.json`
  - QMT 端实际成交：Track B 09:45:01 买入 `300591.SZ 万里马`（fullpool_live rank=1，money_flow_pass=true，research_tier=prefer）；Track A 09:50:02 买入 `002396.SZ 星网锐捷`（p2_dyn_confirm）。
- 部署：无需重新部署到交易端；**明天 05:00 需确认管线正常完成**（timeout 已修复，恢复正常）。
- 备注：救援 watcher 用 `run_at==今天` 作为 pipeline 完成信号存在 30 分钟等待上限，本次在 recommend 中间状态（98 只候选）触发重排，QMT 文件基于该中间池而非最终 141 只——属一次性救援，不影响后续交易日。

## 2026-08-17 Track B fullpool_live 同步：LIVE 模板 + TDX 模拟盘对齐 QMT 模拟盘（v1.2）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_live.py`（QMT 实盘模板 v1.1-tpl → v1.2-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（TDX 模拟盘 v1.1 → v1.2）
  - `track_b/_test_fullpool_live_sync.py`（新增：fullpool_live 同步回归测试）
- 版本变化：QMT LIVE 模板、TDX 模拟盘版本号 +1（逻辑改动）
- 修改内容：
  1. **fullpool_live 逻辑同步**（此前只在 QMT SIM 版存在）：三个文件现在行为一致——
     - 新增常量 `LIVE_FULLPOOL_MIN=09:36` / `USE_SERVER_GATES=True`；
     - `_load_fullpool` 拆分 live/classic 双路径：09:36 后优先读
       `{date}.fullpool_live.json`（服务器 09:35 实时重排池，106 维因子分 +
       资金门 + 研报门已在服务端算好），缺失则回退 classic 05:00 池；
     - 新增 `_fetch_remote_fullpool_live`（09:36 后拉取，与 classic 共享 60s 节流）；
     - 新增 `_live_pool_survivors`：把服务器 live 行映射为内部 survivor
       （rank/score/money_flow_pass/research_tier 原样带入）；
     - `_p2_gate` 加 live 分支：信任服务器 `money_flow_pass`（srv_pass/srv_fail），
       仅保留 QMT/TDX 端实时 ABR 软复核（非硬性否决）；
     - `_check_buy` 决策点从 `DECIDE_MIN`(09:35) 改为 `LIVE_FULLPOOL_MIN`(09:36)，
       live 池就绪后覆盖 classic P1 survivors；
     - init / 日期切换重置 `live_pool_active` / `live_surv_ready`。
  2. **修复存量 bug**：QMT LIVE 模板此前引用 `CALL_DATA_CUTOFF` 但从未定义
     （会导致 `NameError`），现已在常量区补齐（=09:30）。
- 原因/依据：用户询问"Track B 三个策略是否同步更新"。检查发现 fullpool_live
  （服务器实时重排池）逻辑此前只实现于 QMT 模拟盘，QMT LIVE 模板和 TDX 模拟盘
  仍在用 05:00 静态池 + 客户端竞价门控。用户选择"三版本完全一致"。
- 验证：
  - 三个文件 `py_compile` 通过；
  - 新增 `_test_fullpool_live_sync.py`：19 项断言全过（LIVE 常量/映射/资金门
    live 分支/加载路由/09:35 不决策/09:36 覆盖买入 + TDX 纯函数对齐）；
  - SIM 版既有 `_test_buy_window.py` 回归 9 项全过（未破坏）。
- 部署：重新部署 QMT LIVE 模板到各实盘账号目录、TDX 模拟盘到通达信策略目录。

---

## 2026-08-17 服务器部署修复：fullpool_live 导出从未生效（404 根因）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（本地生产版，已含 `--fullpool-live`，服务器端补齐部署）
- 版本变化：无（本地代码未改，补服务器部署）
- 修改内容：
  1. **根因确认**：QMT 模拟盘日志 `[FETCH] fullpool_live fail: HTTP Error 404`。
     SSH 诊断发现服务器 `/home/ubuntu/alphapilot/export_qmt_scores.py` 是**旧版**
     （无 `def export_fullpool_live`），cron 也只有旧的 09:36 无参导出 + 06:30
     `--fullpool` 两条——**`--fullpool-live` 分支与 cron 从未部署过**。
  2. **部署修复**：
     - 服务器旧脚本备份为 `export_qmt_scores.py.bak.20260817`；
     - 上传本地 `production_strategies/server/export_qmt_scores.py`（含
       `--fullpool-live`，13,342 字节，`def export_fullpool_live` 在第 162 行）；
     - 添加 cron `36 9 * * 1-5 ... export_qmt_scores.py --fullpool-live`
       （紧随 09:35 live_momentum_scanner + morning_live_fund_select 之后）；
     - 确认原 09:36 无参 cron（Track A 的 `{date}.json` 导出）仍在，未受影响。
  3. **补跑验证**：手动执行 `python3 -u export_qmt_scores.py --fullpool-live`，
     成功生成 `20260817.fullpool_live.json`（44 只，money_flow_pass=1/44，
     morning_live_at=2026-08-17 09:35:39），nginx curl 验证 HTTP 200。
- 原因/依据：用户报告 QMT 模拟盘 14:34 反复 `FETCH fullpool_live 404`。
  经 SSH 诊断：服务器数据（09:35 重排）实际已正常，只是导出脚本没更新 + cron 没加。
- 验证：服务器 `curl -s -o /dev/null -w '%{http_code}'` → `20260817.fullpool_live.json` = 200；
  内容抽查 Top6 字段（score/money_flow_pass/research_tier/active_buy_ratio/volume_ratio）正确；
  cron 完整性复查：fullpool / fullpool-live / 无参 三条并存。
- 部署：服务器 `150.158.100.236` 已实时生效；QMT 端下一 handlebar 周期自动拉到文件，
  无需重启 QMT（本地文件已落盘 `C:\alphapilot\scores\20260817.fullpool_live.json`）。

---

## 2026-08-17 Track B 买入窗口放宽（v1.0 → v1.1）：09:40 硬截止 → 分段窗口

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（QMT 模拟盘 v1.0 → v1.1）
  - `track_b/TrackB_track_b_qmt_auction_live.py`（QMT 实盘模板 v1.0-tpl → v1.1-tpl）
  - `track_b/TrackB_track_b_tdx_auction_sim.py`（TDX 模拟盘 v1.0 → v1.1）
  - `bt_research/bt_trackb_buy_window.py`（新增：窗口分析脚本）
  - `track_b/_test_buy_window.py`（新增：窗口 mock 回归测试）
- 版本变化：三个策略文件版本号 +1（逻辑改动）
- 修改内容：
  1. **买入窗口**：删除 `DECIDE_END_MIN=09:40` 硬截止，改为两个分段窗口
     `BUY_AM_END_MIN=11:30`（上午 09:36-11:30）+ `BUY_PM_START_MIN=13:00` /
     `BUY_PM_END_MIN=14:00`（午后 13:00-14:00），14:00 后当日不再买入。
  2. **`_top2_fired` 语义**：不再在首次 09:36 扫描后无条件结束当日；只有
     「日预算买满 MAX_DAILY_BUY」或「窗口关闭」才置 True。wait_confirm 候选
     每个 bar 重试。
  3. **永久放弃**：`no_confirm_eod` / `skip_high_turnover` 现在 `sent_today.add()`
     （换手盘中只增不减，不会回落到上限以下）。
  4. **日志节流**：`wait_confirm` 不再打印（放宽后全池 40-80 只每 bar 会刷屏）。
- 原因/依据：用户要求研究是否应放宽买入窗口。回测证据（真实生产 Top10 池
  2026-07-20~07-31，50 个 P2 触发）：首次触发时间分布 09:35-10:00 占 2%、
  10:00-10:30 占 28%、10:30-11:30 占 44%、13:00-14:00 占 20%、14:00-14:57 占 6%；
  **旧 09:40 截止捕获 0/50（0%），Track B 上线以来实际无法买入**。Track A 真实
  成交 9 笔 P2 买入全部在 10:00 后（10:05/11:07/11:09/13:03/13:13/13:30/13:39/
  13:48/14:57）相互印证。各时段收益：午后 13:00-14:00 T+1 最好（+1.80%）；
  尾盘 14:00+ T+1 最差（-3.66%，n=3）故关闭。
- 验证：
  - 三个文件 `py_compile` 通过；
  - 窗口边界单测：09:30-11:30 全放行、11:31-12:59 关闭、13:00-13:59 放行、
    14:00 后关闭（边界逐一断言）；
  - QMT mock 回归测试 9 项全过：09:36 wait_confirm 不放弃、09:41 可买入、
    11:31 关闭、次日 13:30 午后重开可买入、14:01 尾盘关闭、卖出侧不受影响。
- 部署：需重新部署到 QMT 模拟盘 / QMT 实盘模板 / TDX 模拟盘，下一交易日生效。

---

## 2026-08-17 新增文档：轨道 A vs 轨道 B 全链选股策略对比

- 修改人/Agent：主控 Agent
- 涉及文件：`docs/TRACK_A_B_SELECTION_COMPARISON.md`（新增）
- 版本变化：文档新增（无逻辑改动）
- 修改内容：对照两轨「选股 → 买入」全链路：
  1. 全链路时间线对比（05:00 管线 / 06:30 fullpool / 09:25 竞价 / 09:35 重排 / 09:36 fullpool-live / 盘中买入）；
  2. 轨道 A：服务器 Top10 + P2 动态确认 + ABR 门的门槛明细；
  3. 轨道 B：09:36 消费 fullpool_live（服务器 106 维因子 + 资金门 + 研报门）+
     QMT 本地 P2 动态确认；09:36 前 P1/P2 本地竞价门兜底；
  4. 服务器选股明细（05:00 管线门控序列 / 09:35 融合评分 0.6×管线 + 0.4×实时动量 / 资金+研报门）；
  5. 共用 vs 独立环节一览表；静态池 vs 实时池回测对照（已附数据）；文件对照表。
- 原因/依据：用户需求——需要一份文档说明双轨全链选股策略的区别与选股明细。
- 验证：纯文档，无代码改动。
- 部署：无需部署。

---

## 2026-08-17 Track B 实时选股（fullpool_live）：09:36 消费服务器全因子重排池

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `server/export_qmt_scores.py`（新增 `--fullpool-live`）
  - `track_b/TrackB_track_b_qmt_auction_sim.py`（QMT 模拟盘读取 live 池）
- 版本变化：逻辑改动（无版本号递增）
- 修改内容：
  1. **服务器端** `export_qmt_scores.py` 新增 `export_fullpool_live()` /
     `--fullpool-live`：09:36 紧跟 `live_momentum_scanner` + `morning_live_fund_select`
     之后运行，从重排后的 `daily_recommend.json` 导出 `{date}.fullpool_live.json`，
     行字段含 `score`（=0.6×管线106维分 + 0.4×实时资金动量z）、`score_0500`、
     `live_momentum_z`、`money_flow_pass`（服务器资金门）、`research_tier`（研报门）、
     `research_prefer_hit`、`main_net`、`main_net_5d`、`active_buy_ratio`、
     `turnover`、`volume_ratio`、`change_pct`、`pre_market_gap_pct`、`pre_market_action`。
     新鲜度校验：`morning_live_at` 须为今天（09:35 重排已发生）。
  2. **QMT 模拟盘**：新增 `LIVE_FULLPOOL_MIN=09:36` / `USE_SERVER_GATES=True`。
     `_load_fullpool` 拆分为 live/classic 双路径——09:36 后优先加载
     `{date}.fullpool_live.json`（本地或远程 nginx），失败回退 05:00 fullpool；
     决策时点随 live 模式顺延到 09:36（`eff_decide`），09:40 前仍可下单。
     `_p2_gate` live 模式直接采用服务器 `money_flow_pass`/`research_tier`/`score`
     排序门控（106 维因子 + 资金门 + 研报门已服务器端算好），QMT 端只保留
     ABR 实时软复检 + `_p2_decide` 动态确认（价>VWAP、不追高、5m 放量）作为最终触发。
- 原因/依据：用户需求——Track B 不能只看资金/量比，要让 09:35-09:36 实时选股，
  用上 5:00 管线的全部因子与门控。原本 Track B 只消费 06:30 导出的 05:00 静态
  分数，无法反映当日盘中资金轮动（如 2026-08-17 半导体全流入却无一只入选）。
- 验证：
  - 服务器/模拟盘文件 `py_compile` 通过；
  - 用 2026-08-14 真实 `daily_recommend.json` 快照 mock 导出 fullpool_live 成功
    （44 只，money_flow_pass=2）；
  - 本地 mock 单测 4 例通过：live 池加载、`_live_pool_survivors` 映射、
    `_p2_gate` live 排序（money_pass 优先 + score 降序）、classic 回退；
  - 对比回测（2026-08-03~08-14 共 9 天，T+1）：静态池 n=14 胜率 85.7%
    均值 +2.68% 累计 +37.52%；实时池 n=15 胜率 86.7% 均值 **+4.28%**
    累计 **+64.12%**（≈1.7 倍）。样本偏小，方向明确。
- 部署：服务器部署 `export_qmt_scores.py` 并加 cron `36 9 * * 1-5` 跑
  `--fullpool-live`；QMT 模拟盘部署 `TrackB_track_b_qmt_auction_sim.py`，
  下一交易日 09:36 生效（先只验证模拟盘，跑通后推广实盘/TDX）。

## 2026-08-17 Track B 量比门修正：改为「同时段对比」，解决 09:35 结构性误拦

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py`
  - `track_b/TrackB_track_b_qmt_auction_live.py`
  - `track_b/TrackB_track_b_tdx_auction_sim.py`
- 版本变化：逻辑改动（无版本号递增）
- 修改内容：`_get_volume_ratio` 从「今日实时累计量 ÷ 过去5日**全天**均量」改为
  「今日累计量（截至当前）÷ 过去5日**同时段**累计量均值」：
  - QMT（sim/live）：用 5m bar（`count=288`，6 个交易日），`_closed_5m_bars()`
    推算今日已收盘 5m bar 数 k（A股 09:35 起每 5 分钟一根，上午 24 根 + 下午 24 根），
    末尾 k 根为今日累计，往前每 48 根分组取同日 k 根求均值（有多少天用多少天，
    至少 1 天可用即可计算）。
  - TDX：直接用 `tq.get_market_data(period="5m", count=288)` 的 pandas index
    按真实日期分组，`tm <= now_min` 对齐同一时点。
  - 数据不足 / 09:35 前（k=0）→ 返回 `None`（P2 视为软跳过，不拦截）。
- 原因/依据：2026-08-17 模拟盘 09:35 决策时 Top10 全部被 `vr<0.80` 拦截
  （`b_auction_gate.json` 证据），Track B 上线以来从未买入。根因是旧公式在
  09:35 时今日仅交易 5 分钟，`cur/base` 天然 ≈0.03~0.25，永远到不了 0.8；
  Track A 用 5m bar 相对量比（bar 量/自身 5-bar 均量）不受影响，能正常买入。
- 验证：三个文件 `py_compile` 通过；本地 mock 单测（6 例）通过——平量日 09:35
  vr≈1.0 过门、集合竞价 2 倍放量 vr≈2.0 过门、0.3 倍缩量 vr≈0.3 拦截、
  09:30 前返回 None、历史不足仍可计算、10:00(k=6) 对齐正确。
- 部署：需重新部署到 QMT 模拟 / QMT 实盘 / TDX 模拟（替换三个文件），
  下次 09:35 决策生效。

## 2026-08-17 Track B 买入顺延逻辑（资金门不达标 → 顺延下一名，凑满 2 只）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/TrackB_track_b_qmt_auction_sim.py`
  - `track_b/TrackB_track_b_qmt_auction_live.py`
  - `track_b/TrackB_track_b_tdx_auction_sim.py`
- 版本变化：逻辑改动（无版本号递增）
- 修改内容：买入选择从"只试 Top2"改为"**按排序顺延遍历**"：
  1. 原：`picked = [money_pass 的] or p2; picked = picked[:2]` → 只锁死前 2 名，
     第 1 名 P2 动态确认不过就 `continue`，当天不再看第 3、4 名。
  2. 新：`picked = [money_pass 的] + [未通过的]`（`_p2_gate` 已按
     money_pass 优先、score_0500 降序排序），遍历整个候选，谁通过
     P2 动态确认就买谁，直到凑满 `MAX_DAILY_BUY`(2) 或候选耗尽。
  3. 日志：下单打印加 `primary`/`fallback` 标记；`top2 fired` 日志改为
     `scanned=`（截断 180 字符）标明扫描范围。
- 原因/依据：用户："如果 top 选出后资金门没有达到要求，就顺延看哪个
  资金门到要求就选哪个。或者池子里面的股票达到综合要求，排名高的就买"。
  原实现锁定 Top2，资金门/动态确认不达标即当天放弃，不顺延。
- 验证：三个文件 `py_compile` 语法通过。
- 部署：模拟盘 + 实盘 QMT / TDX 策略需重新部署（替换三个文件）。

---

## 2026-08-17 手动持仓止盈止损策略 v1.5.4 → v1.6.0（卖出逻辑对齐全链 v2.12）

- 修改人/Agent：主控 Agent
- 涉及文件：`qmt_stop_loss_tp_v1.6.0.py`（**项目根目录**，非 production_strategies 内；
  这是用户手动选股后由策略自动卖出的独立策略，账号 8886269286）
- 版本变化：v1.5.4 → v1.6.0
- 修改内容：**卖出体系完整对齐全链 TrackA v2.12**，v1.5.4 的固定百分比
  止盈止损（-3/-5/+3/+5/+10、每日 14:50 清仓、主力量比检测）全部替换为全链卖出链：
  1. 异常保护（当日 ≤-21% 不卖）
  2. 跌停保护（当日 ≤-9.7%，T+1 买入日也卖）
  3. T+1 跳过（buy_date 从 POSITION 推断：can_use<vol 视为当日买入，重启后仍生效）
  4. 威科夫买点高潮早退（确认窗口 14:45，次日 09:35-09:50 卖）
  5. VWAP 破位早退（同窗口）
  6. 自适应硬止损（-10% 基准，按 20 日年化波动率缩放约 -8% ~ -15%，14:45 后触发）
  7. T+2 强平 / 延期（14:45，≥95% 成本延期 1 天，否则强平；延期后第 3 天强平）
  8. 动态减仓 peel（+3% 启动跟踪，峰值回撤 1.5% 卖半仓，最多 2 次，每次需创新高）
  同时补齐全链安全特性：订单锁文件（`C:/alphapilot/tpsl_order_locks.json`，
  防重启后重复下单）、可卖数量保护（_do_sell/_do_sell_half 以 can_use 封顶，
  修 v1.5.4 的 T+1 超额卖出风险）、成交日志（`C:/alphapilot/tpsl_trades.json`）。
- 原因/依据：用户只运营该手动持仓策略（不再跑全链自动选股），要求"止盈止损与全链对齐"。
  用户选择"完整对齐"方案：自适应止损 + 移动止盈 + T+2 强平 + 威科夫/VWAP 早退（拿 2-3 天）。
- 验证：`py_compile` 语法通过；纯 ASCII 0 非 ASCII 字节（QMT 加密安全）。
- 部署：需部署到实盘 QMT python 目录（替换 v1.5.4），策略周期 1min。
  注意：v1.6.0 持仓可过夜（T+2），与 v1.5.4 每日清仓不同——这是对齐全链的预期行为。

---

## 2026-08-16 轨道 A/B 策略文件重命名（加 Track 前缀）

- 修改人/Agent：主控 Agent
- 涉及文件（重命名，逻辑零改动）：
  - `track_a/qmt_model_full_chain_v2.py` → `track_a/TrackA_qmt_model_full_chain_v2.py`
  - `track_a/qmt_model_full_chain_template.py` → `track_a/TrackA_qmt_model_full_chain_template.py`
  - `track_a/tdx_full_chain.py` → `track_a/TrackA_tdx_full_chain.py`
  - `track_b/track_b_qmt_auction_sim.py` → `track_b/TrackB_track_b_qmt_auction_sim.py`
  - `track_b/track_b_qmt_auction_live.py` → `track_b/TrackB_track_b_qmt_auction_live.py`
  - `track_b/track_b_tdx_auction_sim.py` → `track_b/TrackB_track_b_tdx_auction_sim.py`
  - 引用同步：`_test_qmt_mootdx.py`（加载路径）、`server/export_qmt_scores.py`（注释）、
    各策略头部命名约定注释、`README.md` 目录/部署表/版本表。
  - **未改名**：`mootdx_feed.py`（同时服务 A/B 且被测试 import，模块名不能改）。
- 版本变化：无（仅文件重命名 + 注释同步）
- 修改内容：用户要求文件名标明轨道。选 **ASCII 英文 `TrackA_`/`TrackB_` 前缀**
  （用户确认；中文文件名在 QMT/TDX 端有编码风险，且 mootdx_feed 等被 import 的模块不能加中文）。
- 原因/依据：用户："最好在最后的文件名称上都标明'通道A'和'通道B'，要不然分不清楚"。
- 验证：QMT 文件（4 份 + 测试）ASCII + 语法校验通过；TDX 文件（2 份）`py_compile`
  语法通过（UTF-8 中文注释，TDX 端无 ASCII 约束）。`_test_qmt_mootdx.py` 9/9 通过，
  `_test_mootdx_feed.py` 仍可 `import mootdx_feed`（模块未改名）。
- 部署：重新部署时按新文件名复制到对应交易端（README 部署对照表已更新）。

---

## 2026-08-16 Track A ABR（主动买占比）门接入策略（QMT 实盘/模拟 + TDX 模拟）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/qmt_model_full_chain_template.py`（v2.12-tpl → v2.13-tpl）
  - `track_a/qmt_model_full_chain_v2.py`（v2.12 → v2.13）
  - `track_a/tdx_full_chain.py`（v2.10 → v2.11）
- 版本变化：三个策略文件均升一版
- 修改内容（每处 4 项，QMT 两份逐行一致）：
  1. **配置**：新增 `USE_ABR_GATE=True` / `MIN_ACTIVE_BUY=0.52` /
     `ABR_GATE_START_MIN=09:30`；QMT 版另加 mootdx feed 配置
     （`MOOTDX_FEED_DIR=C:\alphapilot\l2_feed` / `MOOTDX_FEED_MAX_AGE_SEC=60` /
     `USE_MOOTDX_ACTIVE_BUY=True`）。
  2. **数据函数**：
     - QMT 版新增 `_get_active_buy_from_mootdx`（读 mootdx_feed 当日累计逐笔
       ABR，日累计口径与回测 P2_cum 一致）+ `_get_active_buy_ratio`（mootdx
       优先，回退 QMT L1 120 档逐笔近似：成交价≥卖一=主动买）。
     - TDX 版新增 `_get_active_buy_ratio`（盘口买一档量占比近似，同 Track B
       TDX）+ `_abr_pass` 软门辅助。
  3. **买入门**：`_p2_decide` 触发处加 ABR 门——连续竞价时段（≥09:30）ABR<
     0.52 时返回 `"skip_low_abr"`；TDX 完整版 dyn_confirm 与快照版
     snap_confirm 两个触发点都加。ABR 不可用不拦截（软门）。
  4. **放弃语义**：`_check_buy` 将 `"skip_low_abr"` 纳入当日放弃列表（同
     `no_confirm_eod` / `skip_high_turnover`）。
- 原因/依据：用户拍板"把 Level 2 数据接入轨道 A"。2026-08-16 ABR 回测
  （114 候选 / 20 交易日真实 Top10）：累计 ABR≥0.52 门使 T+1 胜率
  42.3% → 54.2%、T+1 均收益 -0.46% → +0.36%；低 ABR（<0.50）是强负信号。
- 验证：三个文件 `python -m py_compile` 全部通过（SYNTAX OK）。
- 部署：**待用户确认后**再部署到 QMT 模拟端 / QMT 实盘端 / TDX 模拟端。
  QMT 端需配套启动 mootdx_feed.py（独立进程写 `C:\alphapilot\l2_feed\`）。
  默认 0.52 为保守档；若想更严格可改 0.55（T+1 胜率 57.9%）。

---

## 2026-08-16 Track A ABR 回测扩样本 + 卖出早退验证（补充）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/backfill_k5m_aug.py`（**新增**，mootdx freq=0 补 8 月 5m K 线，37 只 → `D:\alphapilot\data\kline5m_full_backfill`）
  - `track_a/bt_abr_sell_early.py`（**新增**，持有期主动卖占比早退回测）
  - `track_a/bt_abr_gate_fullchain.py`（改：双源合并 + backfill 感知）
  - `track_a/BT_ABR_GATE_REPORT.md`（更新：扩样本结果 + 卖出早退结论）
- 版本变化：无（QMT 策略代码未改）
- 修改内容：
  1. 用 mootdx `bars(frequency=0)` 补 8 月 5m K 线（原本地库止于 07-31），37 只约 100s。
  2. 合并候选池：`score_top10_day`（07-20~07-31 完整 Top10）+ `daily_picks_archive`
     （07-26~08-14 门控通过者）→ **20 交易日 / 165 对 / 97 只**，逐笔补拉至 165 文件。
  3. 重跑加门回测：**114 有效候选 / 59 触发**（比首轮 100/50 扩 14%）。
  4. 新增卖出端验证：持有期 ASR（主动卖占比）早退，阈值 0.55/0.60，日累计/近3桶两种口径。
- 原因/依据：用户选择"扩样本复验"。补充 8 月真实生产样本（含 8/14 实际候选），
  并验证 L2 主动卖占比能否用于卖出早退。
- 验证：
  - **买入门（扩样本后更扎实）**：
    - `P2_cum_052`：T+1 胜率 42.3% → **54.2%**（+11.9pp），T+1 均收益 -0.46% → **+0.36%**（由负转正）
    - `P2_cum_055`：T+1 胜率 **57.9%**、T收均 +0.74%（最严门最赚）
    - `P2_win3_050`：T收胜率 **58.5%**（当日最强）
  - **卖出早退（负优化，勿用）**：所有 ASR 变体均差于基线（平均 -1.08~-1.60% vs -0.97%），
    早走单平均亏损（-0.37~-2.27%）。主动卖占比高在弱市常是洗盘，早退卖在低点。
  - **买卖不对称**：ABR 门价值集中在买入确认（排除低 ABR 弱信号），不在卖出。
- 部署：**暂不部署**。买入门建议：P2 加累计 ABR≥0.52 门（或 0.55 更激进）；卖出保持现状
  （Wyckoff BC 已够，勿加 ASR 早退）。待更大样本复验后落地。

---

## 2026-08-16 Track A ABR（主动买占比）门回测验证 + 历史逐笔数据源确认

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_a/fetch_tick_abr.py`（**新增**，mootdx 历史逐笔拉取 + 5m 桶 ABR 聚合）
  - `track_a/bt_abr_gate_fullchain.py`（**新增**，P2 买入 + ABR 门回测）
  - `track_a/_analyze_abr.py`（**新增**，ABR 判别力分析）
  - `track_a/BT_ABR_GATE_REPORT.md`（**新增**，回测报告）
  - 根目录 `bt_research/fetch_tick_abr.py`、`bt_research/bt_abr_gate_fullchain.py`、`bt_research/_analyze_abr.py`（工作副本，与归档一致）
  - `output/bt_abr_gate_fullchain.json`（回测输出）
- 版本变化：无（QMT 策略代码未改；纯研究/验证 + 数据管道）
- 修改内容：
  1. **纠正此前误判**：调研确认 mootdx `transactions()`（非 `transaction()`）底层调用
     `get_history_transaction_data`，可拉**任意历史日期**逐笔，含 `buyorsell`
     （0买/1卖/2中性/5/8竞价）。免费历史 L2 数据存在（mootdx/pytdx/tongstock/easy_tdx）。
  2. `fetch_tick_abr.py`：按 `_top10_dates.json` 计划拉真实生产 Top10 候选池的历史逐笔，
     100 对股×日 78 秒拉完（0 失败），聚合到 `D:\alphapilot\data\tick_abr\{sym}_{date}.json`
     （5m 桶 buy/sell/abr/vol，as-of 不偷看未来）。
  3. `bt_abr_gate_fullchain.py`：在 P2 动态确认（趋势+放量+不追高）基础上加 ABR 门：
     累计 ABR ≥ 0.50/0.52/0.55、近3桶 ABR ≥ 0.50/0.55，对比现状。
  4. 回测窗口：真实生产 Top10 归档 2026-07-20~07-31（10 交易日 / 100 候选 / 49 只）。
- 原因/依据：用户需求——轨道 A 实盘买卖引入 L2 判断主力动向、抓高低点。先回测验证
  "主动买占比门"是否真的提升胜率/盈亏。
- 验证：
  - 回测结果（100 候选 / 50 触发）：
    - `P2_cum_052`（累计 ABR≥0.52）：T+1 胜率 41.9% → **52.6%**，T+1 均收益 -0.57% → **-0.07%**，触发率 50% → 24%
    - `P2_win3_050`（近3桶 ABR≥0.50）：T收均 +0.29%、T收胜率 **55.6%**
    - ABR 判别力：Q1(ABR<0.49) T+1 胜率仅 30.8%、均 -1.54%（强负信号）；排除它 = 剔掉最差批
  - 结论：加门方向正确，机制 = 排除低 ABR 弱信号。样本偏小（50 触发）需更大样本确认。
- 部署：**暂不部署**。当前为研究验证阶段；实盘落地需（a）更大样本复验（b）QMT 侧接入
  mootdx feed（Track B 已有 `_get_active_buy_from_mootdx`，可复用到 Track A）。

---

## 2026-08-16 mootdx 免费逐笔数据接入（替代 L1 主动买近似）

- 修改人/Agent：主控 Agent
- 涉及文件：
  - `track_b/mootdx_feed.py`（**新增**，独立进程，非 QMT/TDX 内置环境运行）
  - `track_b/mootdx_mock.py`（**新增**，离线测试 mock）
  - `track_b/_test_mootdx_feed.py`（**新增**，离线测试）
  - `track_b/_test_qmt_mootdx.py`（**新增**，QMT 接入 seam 测试）
  - `track_b/track_b_qmt_auction_sim.py`（`_get_active_buy_ratio` 改造 + 新增 `_get_active_buy_from_mootdx` + CONFIG 三常量 + P2 gate 输出 `abr_src` 标记）
  - `track_b/track_b_qmt_auction_live.py`（同上，与 sim 逐字一致）
- 版本变化：Track B QMT sim 无版本号（文件头 v1.0 保持）→ 逻辑新增 mootdx 数据源，L1 近似降级为 fallback
- 修改内容：
  1. `mootdx_feed.py`：独立进程，交易日 09:15-15:00 每 20s 轮询候选池逐笔成交（mootdx `transaction()`），按 buyorsell 0=主动买 / 1=主动卖 计算主动买占比，写 `C:\alphapilot\l2_feed\{YYYYMMDD}.json`。支持 `--once` 单次轮询。
  2. `mootdx_mock.py` + `_test_mootdx_feed.py`：离线 mock mootdx Quotes，验证 `_market_code`、`_compute_abr`（含 2/8 中性/竞价剔除）、refresh+save。17/17 通过。
  3. `track_b_qmt_auction_sim.py` / `_live`：新增 `_get_active_buy_from_mootdx(code)` 读本地 feed（60s 内新鲜才算数），`_get_active_buy_ratio` 改为 **mootdx 优先、L1 tick 近似为 fallback**；`USE_MOOTDX_ACTIVE_BUY` 主开关（False 则完全回退旧逻辑）；P2 gate 输出 `abr_src="mootdx"/"l1"` 便于周一验证数据源是否生效。
- 原因/依据：用户需求——无 QMT L2 权限（太贵），本地通达信 L2 仅显示不可导出（8/16 实探确认：零落盘），PTrade L2 仅实盘环境可用（模拟盘不可用，用户 8/16 提供文章佐证）。mootdx 免费连接通达信行情服务器取逐笔，含买卖方向，是最可行的"近似 L2"。今日为周日非交易日，仅完成代码 + 离线验证，实时验证推迟到下一交易日。
- 验证：
  - ASCII：sim/live 两个 QMT 文件纯 ASCII ✅；`mootdx_feed.py` 等独立进程文件 UTF-8 合法（不跑 QMT 解释器，无需 ASCII）
  - 语法：全部通过 ✅
  - 离线测试：`_test_mootdx_feed.py` 17/17 ✅；`_test_qmt_mootdx.py` 9/9（新鲜优先、stale 回退、缺失回退、开关关闭回退、L1 fallback 0.5 正确）✅
  - sim/live 一致：mootdx 三处逻辑块逐字一致 ✅
- 部署：**需要**。
  - `track_b_qmt_auction_sim.py` / `track_b_qmt_auction_live.py` → 重新同步到 QMT 模拟盘 / QMT 实盘模板
  - `mootdx_feed.py` → 放在本机独立 Python 环境（装有 mootdx），交易日 09:15 启动，作为独立进程常驻
  - 周一交易日：启动 feed 后看 `C:\alphapilot\l2_feed\{date}.json` 是否更新 + QMT 日志 gate 的 `abr_src` 是否为 `mootdx`

---

## 2026-08-16 同步归档规则给所有 Agent

- 修改人/Agent：主控 Agent
- 涉及文件：`docs/AGENT_RULES.md`（新增）、根目录 `.cursor/rules/production-strategies.mdc`（新增）、根目录 `AGENTS.md`（新增一节）、`README.md`（目录结构同步）
- 版本变化：无（规则/文档类）
- 修改内容：
  1. 新增 `production_strategies/docs/AGENT_RULES.md`：给 DeepSeek Harness / WorkBuddy 等外部 Agent 的修改约束（只改归档文件夹、必须写日志、纯 ASCII、交付清单、历史已知问题 B1-B4/F1-F3、F3 保留不改）。
  2. 新增 `.cursor/rules/production-strategies.mdc`：Cursor 项目级规则（alwaysApply），约束所有 Cursor Agent 在本项目内自动遵守归档规则。
  3. `AGENTS.md` 新增「生产策略归档（唯一权威来源）」一节，所有 Agent 入口可见。
- 原因/依据：用户要求把归档规则同步给 DeepSeek Harness，确保其他 Agent 修改时也走同一文件夹 + 日志流程。
- 验证：文档类改动，无代码影响。
- 部署：不涉及。

## 2026-08-16 归档建立 + F1/F2 修复

- 修改人/Agent：主控 Agent
- 涉及文件：全部（新建 `production_strategies/` 归档文件夹）
- 版本变化：基线见 `README.md` 第六节
- 修改内容：
  1. 建立 `production_strategies/` 归档，收入 6 个策略文件 + `export_qmt_scores.py` + 2 份文档。
  2. **F1 修复（板块聚合性能）**：`track_b_qmt_auction_sim.py` / `track_b_qmt_auction_live.py` / `track_b_tdx_auction_sim.py`
     - QMT 版：`_sector_constituents` 结果缓存到 `C._sector_members_cache`（盘中静态，每天只拉一次）；每板块抽样上限 `SECTOR_AGG_MAX_MEMBERS=30`；个股 gap 写入 `_gap_cache` 且带 `now_min<=CALL_DATA_CUTOFF` 时序保护；每日换日重置缓存。
     - TDX 版：`_aggregate_sector` 接受 `now_min`，gap 写入 `ST["gap_cache"]` 带时序保护（原先只读不写，每轮重复拉行情）。
  3. **F2 修复（TDX 主动买边界）**：`track_b_tdx_auction_sim.py` 的 `_get_active_buy_ratio`——`bv`/`sv` 任一字段缺失时返回 `None`（软跳过），不再强设为 `0.0` 导致 P2 资金门误硬堵。
- 原因/依据：DeepSeek Harness 代码交叉验证报告（`docs/CODE_CROSSVALIDATION_BRIEFING.md` + 外部报告）F1/F2 发现；F3（拒单后不重试）经用户确认保持现状。
- 验证：
  - ASCII：3 个修改文件全部纯 ASCII ✅
  - 语法：全部通过 ✅
  - 离线回归：`_test_tdx_b.py` 8 项全过（含新增 F2 专项测试：买侧/卖侧缺失→`None`，双字段齐全→正常比值）✅
  - sim/live 一致性：QMT 轨道 B 相似度 97.4%（仅配置 + README 差异）✅
- 部署：**需要**。将 `track_b/` 下 3 个文件重新同步到 QMT 模拟盘 / QMT 实盘模板 / TDX 量化端。

## 2026-08-16 初始归档

- 修改人/Agent：主控 Agent
- 涉及文件：全部
- 版本变化：无（首次归档）
- 修改内容：将项目根目录的 6 个生产策略文件 + 服务器导出脚本 + 设计/验证文档归档到本文件夹，建立「唯一权威来源」。
- 原因/依据：用户要求所有落地生产文件统一归档，后续修改都在本文件夹进行并写日志。
- 验证：逐文件 ASCII + 语法通过（`tdx_full_chain.py` 含中文注释，UTF-8 合法，仅 TDX 平台运行）。
- 部署：不涉及（归档动作本身）。
