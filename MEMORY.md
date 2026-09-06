# AlphaPilot 项目长期记忆（Cursor ↔ WorkBuddy 共享）

> 双方 Agent 必读。结论性规则写这里；详细论证见 `knowledge/` / `docs/`。
> 最后更新：2026-09-06

---

## 服务器操作分工约定（2026-09-06 用户拍板）

**原则：需要上传服务器 / 在服务器上做变动的，Agent 直接执行，不再询问、不交给用户。**

- 背景：服务器（上海 ECS `/home/ubuntu/alphapilot`）的上传/变更历来由 Agent 完成，用户从未参与。
  如果让用户手动操作，容易漏传（资金三角影子 9 天空转的根因之一就是模块漏传服务器）。
- 适用范围：**服务器端一切文件与操作**（scp 覆盖、补传模块、cron 变更、运行脚本等）→ Agent 直接做。
- 例外（仍由用户手动）：**交易端文件**（QMT python 目录 / TDX `PYPlugins\user`）— 见
  `.cursor/rules/production-strategies.mdc` 规则 5「部署由用户手动执行」，用户会自行复制/导入模拟端与实盘端。
- 执行纪律：Agent 每次服务器变更后照常自验（py_compile / md5 比对 / 关键字段计数），并在 CHANGELOG / checkpoint 留痕。

---

## 日常验证分工约定

**生效日：2026-08-26 起。** 原则：**PASS 静默、FAIL 才报。** 全绿 = 当没这回事。

| 环节 | 状态 | 职责 |
|---|---|---|
| 上传前校验 | ✅ 已上线 | WorkBuddy — `_upload_chip_template.py` 内嵌 `check_chip_batches.py`，FAIL 即 `exit(1)` 物理拦截 |
| 服务器闸门 | ✅ 已上线 | Cursor/服务器 — `18:15 daily_coverage_check` + `04:50 data_readiness_gate` cron 自动跑 |
| 失败才告警 | ✅ 已上线 | Cursor/服务器 — `data_readiness_gate` 仅 critical **FAIL** 推 WeCom；`ready=True` 静默（同日同 sig 去重） |
| WorkBuddy 侧报告 | ✅ 已上线 | WorkBuddy — PASS 不发「今日已通过」长报告；FAIL 才主动报 |

**用户侧**：不再每天问「数据拉好没」。只有失败（校验 FAIL / 上传失败 / WeCom 告警 / 05:00 管线异常）才打扰。

**08-24 半截上传事故整改**：至此封口（2026-08-25 闭环确认）。

关联文档：
- `production_strategies/docs/WORKBUDDY_CHIP_UPLOAD_RULES.md`
- `production_strategies/server/check_chip_batches.py`
- `scripts/data_readiness_gate.py`（`maybe_wecom_push_fail`，`WECOM_READINESS_PUSH=0` 可关）
- `docs/WB_筹码上传校验报告_2026-08-25.md`
- `docs/LOG_2026-08-25.md`

---

## K 线单位铁律（2026-08-22 用户拍板）

**判定统一用 `amount / (volume × close)`：**

| ratio | 含义 | 动作 |
|---|---|---|
| ≈1 | 已是股 | **别动** |
| ≈100 | 是手 | **×100 转股** |

- 缓存口径 = **股**；通达信源 = **手**。
- 禁止仅凭列名判断；ratio≈100 才 ×100。
- **WorkBuddy**：K 线只读不写；归 cron `15 16 * * 1-5` + 已部署 `fix_kline_server.py`。

详述：`docs/CURSOR_K线单位铁律_2026-08-22.md`

---

## 关键数据发现

- 生产 chip **只认 WorkBuddy 上传的东财真实 CYQ**，不用 `pull_chip_from_kline.py` 推演兜底。
- 服务器数据真相以 **SSH 上海机** `data_readiness_gate.py` 为准，不以本地 stale 文件为准。
- 生产模型 = V25 **106 维**（不是 fd1 实验 116 维）。

---

## 选股模型 vs 买卖模型（必须分开讲）

- **选股模型** = 服务器（05:00 管线 / 09:35 scanner / 09:36 导出）。决定候选池和排名。改选股 **不用改** QMT/通达信。
- **买卖模型** = QMT / 通达信。读 `{date}.candidates.json` Top10，P2 确认后下单、再按规则卖出。只有改 P2/仓位/卖出才动交易端。
- 网页融合 Top10 是选股展示榜，**不是**买卖模型的下单顺序。
- 详述：`knowledge/strategies/selection_vs_execution.md`
- **Checkpoint 目录**（做过什么 / 还要盯什么）：`knowledge/ops/checkpoints.md`

## 生产策略唯一权威来源

`production_strategies/` — 轨道 A/B 落地代码只改此目录；根目录同名文件冻结。

---
