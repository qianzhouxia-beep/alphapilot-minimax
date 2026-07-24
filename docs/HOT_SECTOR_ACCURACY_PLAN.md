# 准确率优化：热门板块召回（Top1–3）

日期: 2026-07-23  
目标: 提高 Top1/2/3 **准确率**（胜率 / hit≥3%）；解决「热门票被滤光 → 留下慢涨票」

## 问题判断

1. 板块门控生产已是 `soft_dual`（deny 降权不删），主因不全是 dual 硬杀。  
2. **近涨停过滤在截断之后直接删、不补位** → 热门票一踢，池子变冷。  
3. VM 排序对「当日主线」加权不足 → Top1–3 不够热。

## 已落地（生产，明早 05:00）

| 改动 | 作用 |
|------|------|
| `hot_sector_prefer_boost.py` | allow 行业 ×1.08、仅概念 allow ×1.04，再排序 |
| 近涨停 **跳过并向下补位** | 踢掉买不到的票后，用后面可买的票填满池 |
| 软宇宙（此前） | 启动\|旁路不硬删，默认 mult=1.0 |

回滚:
```bash
ENABLE_HOT_SECTOR_PREFER=0 ENABLE_SOFT_UNIVERSE=0 python3 -u alphapilot_pipeline_v3.py
```

## 验收口径（只看 Top1/2/3）

- win_rate、hit≥3%、hit≥5%  
- TopK 中 `hot_sector_prefer` 占比（主线覆盖）  
- 对照脚本后续可加：`scripts/compare_hard_vs_soft_universe.py` 扩展

## 下一步（RD-Agent / 参数搜索）

在固定 Top1–3 回测上搜：`HOT_SECTOR_INDUSTRY_BOOST`、宇宙 mult、资金弱硬阈值——**先看样本外准确率，再动训练特征**。
