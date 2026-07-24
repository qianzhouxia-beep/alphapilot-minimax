# 盘中万得精度提升

日期: 2026-07-23  
目标: 提高盘中指数/个股资金精度，服务盘前选股、早盘下单、午评、B 臂软分、14:45 尾盘狙击。

---

## 做了什么

| 时段 | 动作 | 产出 |
|------|------|------|
| **04:30** | 个股 B′ 盘前预热（≤80） | `wind_candidate_flow.json` session=premarket |
| **09:35** | 个股 B′ 开盘刷新（≤80） | session=open，供早盘下单 / trade_precheck |
| **11:35** | 板块流 + 个股 B′（≤80） | `wind_board_flow.json` + `wind_candidate_flow.json` |
| **14:25** | 再刷板块 + 个股 B′（≤80） | 同上 + `wind_board_flow_pre_eod.json` |
| **15:10** | 收盘板块（写 history） | 连续天数口径归档 |
| **15:30** | `refresh_all_data` 内仍 enrich 一次 | 盘后兜底 |

个股字段增强：主力净流 + **机构/大户/中户/散户**；`money_flow_gate` 写入 `wind_*_net`，机构净流入且主力>0 → 软分 +0.02。

**下单前**：`trade_precheck.intraday_fund_confirm` 读 `wind_candidate_flow.json`（不额外耗积分）：
- 机构+主力同向流入 → weight ×1.12
- 散户追涨/机构未跟 → ×0.72
- 机构深流出 → ×0.70

编排脚本：`scripts/refresh_wind_intraday.py`  
安装：`bash scripts/install_wind_intraday_cron.sh`

---

## 积分粗估（日）

| 项 | 次 | 约分 |
|----|----|------|
| 板块 ×3（午/尾前/收） | ~52×3 | ~94 |
| 个股 ×4（盘前/开盘/午/尾前，≤80）+ 盘后 | ≤80×5 | ≤240 |
| trade_precheck Wind | 0（读缓存） | 0 |
| **合计** | | **~300–350 / 1000** |

仍留大半缓冲。

---

## 明确不做

- 不全 A 扫个股  
- 不改硬 avoid / 资金硬门口径一刀切  
- 不替换东财全市场盘口

---

## Watch

- 日志：`output/logs/wind_intraday.log`  
- 04:30 / 09:35 / 11:35 / 14:25 后 `updated_at` / `session` 应更新  
- 14:45 前 `wind_candidate_flow.json` 的 `updated_at` 应接近 14:25  
- 样本股是否带 `wind_inst_net` / `wind_tier_bias`；下单日志里 `fund_confirm.wind_tier_bias`
