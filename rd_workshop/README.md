# Model R&D Workshop

独立于生产 Task Chain（ADR-0001 / ADR-0002）。

## 两套方案（并行）

```text
Track A: Current Model Uplift          Track B: RD-Agent Self-Dev
  现有 VM2.5 特征空间增量挖因子            RD-Agent 独立假设/写码/回测
  track_a_current_model_uplift.py          track_b_rdagent_self_dev.py
                 \                        /
                  \                      /
                   v                    v
              Promotion Adapter (共享出口)
              run_promotion_adapter.py
                   |
            Human Review → Promotion?
```

| | Track A | Track B |
|--|---------|---------|
| 目标 | 抬升**当前生产模型** | **自研**新因子配方 |
| 依赖 | 生产只读数据 + `features_v2` | RD-Agent / Qlib（可另环境） |
| 产出 | `rd_a_*` 因子表 | RD-Agent 导出 → `rd_*` |
| 上线 | 同一晋升适配器 + 人工审核 | 同左 |

## 目录

```
rd_workshop/
  track_a_current_model_uplift.py
  track_b_rdagent_self_dev.py
  run_promotion_adapter.py      # 共享晋升出口
  normalize_factors.py
  data_support/inbound/
  candidates/<run_id>/
  rdagent_runs/                 # Track B 工作区（若本地跑 rdagent）
```

## 命令

```bash
# Track A：挖增量因子（可加 --promote 直接进候选训练+OOS）
python3 -u rd_workshop/track_a_current_model_uplift.py --sample 300 --top-k 10
python3 -u rd_workshop/track_a_current_model_uplift.py --promote --max-stocks 80

# Track B：环境检查 / 导入 RD-Agent 导出并晋升
python3 -u rd_workshop/track_b_rdagent_self_dev.py --doctor
python3 -u rd_workshop/track_b_rdagent_self_dev.py --from-export path/to/factors.parquet --promote

# 共享出口（手动）
python3 -u rd_workshop/run_promotion_adapter.py --factors ...
```

## 硬约束

- 两套方案**互不改对方任务链**，也**不改生产 cron / models / 模拟盘**
- 可以互相提供只读数据（例如 Track B 参考生产 OOS 基线）
- 只有 `PROMOTION_CHECKLIST.md` 人工勾选通过后，才允许安装进生产 `models/`

## 定时执行

详见 [`SCHEDULE.md`](./SCHEDULE.md)。安装：`bash rd_workshop/install_crontab.sh`

| 时间 | 任务 |
|------|------|
| 周六 02:00 | Track A 挖因子 + 候选训练 + OOS |
| 每月 1 日 03:00 | Track B 环境体检 |
| 工作日人工 | 对照报告决定是否 Promotion |
