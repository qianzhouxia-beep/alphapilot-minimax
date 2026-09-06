# 情报层（OSINT 隔夜情报 + 异动归因）落地

> project: alphapilot | domain: architecture | status: conclusion
> date: 2026-08-18 | tags: 情报层, 隔夜, 异动归因, 微信推送

## 结论

借鉴 Crucix（开源 OSINT 终端）为 AlphaPilot 增加"情报"能力，**阶段 0 + 阶段 1 + 阶段 3 已于 2026-08-18 上线**，今天 5:00 选股管线生效。

## 落地内容

| 文件 | 职责 |
|---|---|
| `intel_sweep.py` | 扩源采集：A50（新浪 hf_CHA50CFD）、恒指/恒生科技（腾讯 qt）、金银铜油（新浪 hf_GC/SI/HG/CL）、国内快讯（东财 getFastNewsList）、合并美股/美债（us_enhanced_factors.json）→ `output/intel_prebrief.json` |
| `intel_map.py` | 板块↔事件映射表（EVENT_SECTOR_MAP，10 类事件）+ `risk_assessment` 评估（normal/elevated/high/extreme + suggest_expo_cap） |
| `scripts/intel_brief.py` | 盘前简报生成（markdown）+ 微信推送（wecom_push） |
| `intel_anomaly.py` | 盘中异动归因：情报事件 ↔ 盘中板块告警匹配 → `output/intel_anomaly.json` |

## 接入点（已上线）

1. **5 点管线**：`alphapilot_pipeline_v3.py` 第 0 步后新增 0b 步骤跑 `intel_sweep.py`（不阻断，60s 超时，失败仅告警）。
2. **盘前推送**：cron 08:50 `intel_sweep.py && intel_brief.py`（先刷最新 A50/快讯再推送），已真实推送验证 ok=True。
3. **盘中归因**：cron 10:00/11:00/13:30/14:30 与 `intraday_sector_watch.py` 联动追加 `intel_anomaly.py`。

## 关键原则

- **只产出上下文，不改生产选股结果**：`risk_assessment.enabled=False`、`INTEL_SECTOR_BOOST=0` 默认关。
- 逐源容错、优雅降级（任何源缺失简报仍可推送）。
- 盘中归因只做解释，不改 `trade_executor` 卖出信号。

## 数据源事实（实测）

- ✅ 可用：A50、恒指/恒生科技、金银铜油、东财快讯（7x24，含地缘类真实事件）、美股/美债（已有）。
- ❌ **美元指数源不可用**（Yahoo/东财/新浪均失败）→ 降级用美债 10Y 变化代替。
- 干跑实测全程 ~0.3s，8 条快讯正常返回。

## 验证期指标

- 简报对当日板块方向命中率 ≥ 60% 才考虑接入门控（阶段 1.5，从 08-18 起积累样本）。

## 待办

- [ ] 跑 2 周验证命中率
- [ ] 门控接入（INTEL_EXPO_CAP_ENABLE / INTEL_SECTOR_BOOST 默认关）
- [ ] 盘中告警命中事件时 FLASH 级即时推送（当前只落盘）
- [ ] 事后复盘：异动↔事件对应关系入库
- [ ] 命中率验证脚本 `scripts/intel_hit_rate.py`
