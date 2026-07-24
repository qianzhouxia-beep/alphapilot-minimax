# Model R&D Workshop 执行时间表

生产 Task Chain（05:00 选股 / 09:35 资金重排 / 模拟盘）与研发车间**分轨**。  
下表只描述 **Workshop**；**不会自动改生产 `models/`**。

## 当前排程（VM crontab）

| 时间 (Asia/Shanghai) | 任务 | 说明 |
|----------------------|------|------|
| **周六 02:00** | Track A | `track_a_current_model_uplift.py --sample 400 --top-k 10 --promote`：挖增量因子 → 候选训练 → 可交易 OOS → 写出 `promotion_report` |
| **每月 1 日 03:00** | Track B 体检 | `track_b_rdagent_self_dev.py --doctor`：检查 RD-Agent 环境；有导出时人工 `--from-export --promote` |
| **工作日（人工）** | Human Review | 对照 `rd_workshop/candidates/*/promotion_report.json` 与生产 OOS；勾选 `PROMOTION_CHECKLIST.md` 后才可 Promotion |

## 与生产的关系

```text
周六凌晨 Workshop 产出 Candidate
        ↓
工作日人工审核（对比生产模型）
        ↓  仅当批准
手动安装到 models/（Promotion）
        ↓
次日 05:00 生产管线才可能用到新模型
```

## 尚未自动的部分

- Track B 全量 `rdagent fin_quant`：需先 `pip install rdagent` + Qlib 数据，再按需手动或另加 cron。
- **禁止**把 Workshop 脚本挂进 09:36 交易链或自动覆盖 `models/`。

## 日志

- Track A: `output/logs/rd_track_a.log`
- Track B doctor: `output/logs/rd_track_b_doctor.log`
