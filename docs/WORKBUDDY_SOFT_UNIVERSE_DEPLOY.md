# WorkBuddy 同步：软宇宙已上生产实验默认

日期: 2026-07-23  
来自: Cursor（主人批准「继续」）

## 已做

1. SoftUniverse / Pure 回测完成（见 `output/SOFT_UNIVERSE_V1.md`）。
2. **生产实验已部署**（明天 05:00 管线生效）:
   - `soft_universe_gate.py`
   - `alphapilot_pipeline_v3.py` 宇宙门改为调用软宇宙
   - 默认 `ENABLE_SOFT_UNIVERSE=1`，`SOFT_UNIVERSE_MULT=1.0`（跟回测 Pure）
3. 对照脚本: `scripts/compare_hard_vs_soft_universe.py`

## 回滚

```bash
# crontab 可改为：
cd /home/ubuntu/alphapilot && ENABLE_SOFT_UNIVERSE=0 python3 -u alphapilot_pipeline_v3.py >> output/logs/pipeline_0500.log 2>&1
```

## 请你继续

1. 照常跑 P0「大涨票死在哪一层」表（可与软宇宙交叉验证）。
2. 明早看 `pipeline_0500.log` 是否出现 `软宇宙入口` / `[AUDIT]`。
3. 跑 `python3 -u scripts/compare_hard_vs_soft_universe.py`，把 soft_only_in_top 记一笔。
