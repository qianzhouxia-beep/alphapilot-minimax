# 算力分工：上海=生产机 / 新加坡=重算力沙箱

- **日期**：2026-09-13
- **状态**：已定调（用户拍板）
- **决策人**：老板（提出新加坡方案 + "行的话就写进规则，以后统一"）
- **执行**：Cursor
- **关联**：`.cursor/rules/compute-host.mdc` · `MEMORY.md` · `scripts/sg_sandbox.py` · `rd_workshop/walkforward_oos.py`

## 1. 问题

在**上海生产机**（`150.158.100.236`，**3.6 GB 内存**）上跑全市场 walk-forward OOS：
- `baseline_full_0913`：处理到 3/6 折被 **OOM killer 杀**（`anon-rss 3.14 GB`）；
- `baseline_full_0913b`：内存优化后仍在**建面板阶段**被杀（`anon-rss 3.14 GB`）。

生产机被重算力任务反复打满，**有连累生产链路（05:00 管线 / 09:35 scanner / cron）的风险**。

老板原话：

> 「你是在服务器上跑的回撤吗？所以才被卡，所以才被杀掉的吗？……如果是跑回撤、跑数据，你可以去新加坡服务器看看，那边内存可能比较大一点。……如果行的话，在新加坡那边跑完回撤以后，就把它写进规则里面。写到规则里面以后就不会一会儿这里、一会儿那里的，以后就统一了。」

## 2. 方案：算力分工

| | 上海 `150.158.100.236` | 新加坡 `43.156.119.47` |
|---|---|---|
| 定位 | **生产机** | **重算力沙箱** |
| 内存 | 3.6 GB | **15.6 GB（12.4 GB 可用）** |
| 核 / 磁盘 | 小 | 4 核 / 178 G（134 G 空闲） |
| 跑什么 | 05:00 管线、09:35 scanner、cron、闸门 | 回测 / walk-forward / 训练 / 因子挖掘 / 批处理 |
| 数据 | **权威源**（只被拉取） | 镜像（从上海单向下拉） |

## 3. 沙箱实现（`/home/ubuntu/bt_sandbox/`）

```
bt_sandbox/
├── alphapilot/        # 代码+数据镜像（ALPHAPILOT_ROOT）
│   ├── *.py           # 根级代码（534 个）
│   ├── rd_workshop/   # 研发脚本（13 个）
│   ├── data/          # kline_all.parquet, fund_flow, margin, event, lhb, chip, fundamental
│   └── models/        # v25_opt_ensemble_{1,2,3}.ubj, v25_meta, best_tech_params
└── pylibs/            # pip --target 安装的锁定版本依赖（PYTHONPATH）
```

**关键点：版本锁定。** SG 系统默认 Python 3.12 + **pandas 3.0.3** + xgboost 3.3.0，与生产（pandas 2.3.3 / xgboost 3.2.0）不同 ⇒ 直接跑结果**不可比**。故用 `pip install --target` 装生产同版本：

| 依赖 | 生产 | 沙箱（锁） | SG 系统默认（弃用） |
|---|---|---|---|
| Python | 3.10.12 | 3.12 | 3.12 |
| numpy | 2.2.6 | 2.2.6 | 2.5.1 |
| pandas | 2.3.3 | 2.3.3 | **3.0.3** |
| xgboost | 3.2.0 | 3.2.0 | 3.3.0 |
| sklearn | 1.7.2 | 1.7.2 | 1.9.0 |
| scipy | 1.15.3 | 1.15.3 | 1.18.0 |
| pyarrow | 24.0.0 | 24.0.0 | 25.0.0 |

（`python3-venv` 在 SG 不可用 → 用 `pip --target` 替代，不污染系统环境。）

## 4. 验证：忠实复现（关键证据）

300 只 × 2 折 smoke，**SG 与上海结果 16 位小数完全一致**：

| | 上海 `smoke_0913c` | 新加坡 `sg_smoke_0913` |
|---|---|---|
| 折1 cand AUC | 0.6827003460611245 | **0.6827003460611245** |
| 折1 cand IC | 0.033492613098934546 | **0.033492613098934546** |
| 折2 cand AUC | 0.6568263315806313 | **0.6568263315806313** |
| 折2 ΔAUC | −0.00808 | **−0.00808** |

⇒ 沙箱不是「另算一套」，是**同口径算力外移**。RSS 1.08 GB（上限 15.6 GB），彻底消除 OOM。

## 5. 操作约定

```bash
# 同步本地代码（repo-first）
python3 scripts/sg_sandbox.py --sync
# 从上海拉数据/模型（单向）
python3 scripts/sg_sandbox.py --sync-data
# 跑
python3 scripts/sg_sandbox.py --run "rd_workshop/walkforward_oos.py --folds 6 --test-days 21 --run-id baseline"
# 取产物
python3 scripts/sg_sandbox.py --fetch rd_workshop/walkforward_runs/<id>/report.json ./_sg_out/
```

- 重活加 `nice -n 10`（SG 还跑着 crypto 纸盘 / HK 纸盘）。
- **绝不反向写上海生产数据**；沙箱产物留 SG。
- 报告/结论仍引上海生产口径。

## 6. 边界与风险

- SG 同时承载 **crypto 纸盘（Binance 测试网真实下单）** 与 **HK 纸盘**；重算力已 `nice`，但**若未来 SG 负载升高，需重新评估**（或给回测单独限核 `taskset`）。
- 沙箱数据是**快照**：会随上海更新而滞后。跑研究前若要最新数据，先 `--sync-data`。
- 版本锁定是**可比性前提**：生产升级依赖时，沙箱 `pylibs` 必须同步重建。
- 这不是「数据源迁移」：港美股数据归属 SG 是 2026-09-10 的**另一条**决策（`knowledge/inbox/2026-09-10-hk-us-phase0-probe.md`），与本条（A 股重算力外移）**不同**，勿混。
