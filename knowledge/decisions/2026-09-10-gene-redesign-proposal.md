# gene 重排公式重设计 — 提案

> 状态：**NO CHANGE RECOMMENDED（不推荐任何生产变更）** ｜ 2026-09-10
> 依据：`knowledge/inbox/2026-09-10-gene-redesign.md`（19 个月双代理池 + 30 天真实 Top10 留出）
> 生产文件：**未改**。`production_strategies/` 只读，未部署。

## 决定

**保持现行 gene 不变，不部署任何新公式。**

`export_qmt_scores.py::_gene_rerank_candidates` 的
`gene_score = rank(limit_cnt_10d) + rank(ma25_slope) + rank(ret_10d)`（等权 rank-sum，T-1）**维持原样**。

理由（三条，缺一不可）：

1. **没有变体在两个代理池同时通过样本外**（OOS top-3 uplift>0、OOS IC5 t≥2、真实留出>基线）。
2. **多重检验不过关**：最好的变体（P2 `LOWACT6_only`，OOS top-3 uplift +0.0197）低于「同一因子池 25 变体族随机取最大」零分布的 p95（0.0258），family-wise 经验 p = 0.50（P1 = 0.81）→ **不能声称超过随机搜索**。
3. **方向对出场口径高度敏感**：现行 gene 在 `close(T+1)` 口径下 19 个月 +266%，在 `+3%锁盈/−4%止损` 日频代理下 −54%。低活跃倾斜只在锁盈口径加分。这不是稳定 alpha，是赔付函数产物。

## 但必须同时记录的反向事实（不要误读成"gene 已验证"）

- 现行 gene 在三类样本的**方向性证据全部不利**：
  - 代理池样本外 fwd5 IC 为负：P1 −0.0116（t −1.08）、P2 **−0.0328（t −2.70）**；
  - dev 窗口拟合的 IC 权重**全为负**（lim10 −0.051/−0.059、ret10 −0.043/−0.034、ma25_slope −0.027/+0.004）；
  - 真实 30 天 Top10 留出排序力≈0（IC +0.011，t 0.17）；top-3 真实 `abs3_trail` 收益 0.873%。
- 故本决定应表述为 **"保持现状（pending），而非确认有效"**。gene 的原始依据是 2026-09-03 的 34 天真实样本甜区；本卡未能用更大的样本外证据复现该方向。

## 唯一登记的影子候选（**不部署**）

`GENE_plus_LOWACT6`：在现行 gene 的 3 个成分上，追加 triage 存活的低活跃 6 因子（符号按 triage，低值优先）。

- 在 P1 / P2 / 真实留出**三个样本的配对差值均为正**，是唯一族内三样本符号一致的候选；`GENE_plus_LOWACT6_icw` 的 OOS IC 最高（P2 +0.0568, t 4.28）。
- 但**从未单独显著**：P1 配对 diff +0.0110 CI[−0.0067, +0.0290]；P2 +0.0194 CI[−0.0014, +0.0398]；留出 +1.33pp CI[−0.61, +3.29]。

**触发条件（满足后才进入提案评审）**：真实 Top10 归档累计 **≥90~120 个交易日**，在同一 harness（`bt_research/bt_gene_redesign.py holdout`）上重跑，要求 `GENE_plus_LOWACT6` 对 `GENE_base` 的配对 95% CI 排除 0，且在 ≥100 日样本上不依赖出场口径。

## 附录：若将来触发，改动规格（仅供参考，当前禁止部署）

- **插桩点**：`production_strategies/server/export_qmt_scores.py::_gene_rerank_candidates`（`gene_score` 那一行，约 L336）。
- **字段**：全部已在该函数 `_load_t1_path_frame` 的 T-1 frame 中，或可用同口径一行算出：
  - 现有：`limit_cnt_10d`、`ma25_slope`、`ret_10d`
  - 需新增（与 `bt_factor_triage.py`/本 harness 定义一致，T-1 收盘）：
    `turnover`（换手率，已有列）、`box20=((high20−low20)/close)`、`atr14=(TR14/close)`、`ret_std20=std(ret1,20)`、`shrink_days`（`volume<vol_ma20` 连续天数）、`vol_5_20=vol_ma5/vol_ma20`
- **公式**（等权 rank-sum，`rank(pct=True)`；`LOW=` 低值优先进 rank）：
  ```
  gene2 = rank(limit_cnt_10d) + rank(ma25_slope) + rank(ret_10d)        # 现行 3 项，权重不变
        + rank(-turnover) + rank(-box20) + rank(-atr14)
        + rank(-ret_std20) + rank(shrink_days) + rank(-vol_5_20)
  ```
  缺失值按现行做法填 `rank.median()`。
- **排序键不变**（保住 path_fade/loud_vol 降权与 sns 次级键）：
  `sort by path_fade asc, loud_vol asc, gene2 desc, sns_score desc, rank_raw asc`。
- **影响面**：仅服务器选股导出（`{date}.candidates.json` 的 rank 顺序）；网页融合榜、`{date}.json` 顺序不变；交易端不需要改（如果仍维持 `MAX_CAND_RANK=3`）。
- **需重算的部署清单**：`export_qmt_scores.py` → 服务器 `alphapilot`（`production_strategies/server/` 为唯一权威来源），并追加 `CHANGELOG.md`；本卡不执行。

## 未做 / 明确排除

- 未改 `production_strategies/`、未改 cron、未部署、未碰 `track_a/`。
- 未做市值/行业中性、未做容量/滑点；代理池 ≠ 真实模型 Top10。
