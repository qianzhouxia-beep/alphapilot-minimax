# K 线单位铁律 — Cursor 侧落地回执

日期: 2026-08-22
关联: `docs/CURSOR_K线单位铁律_2026-08-22.md`（WorkBuddy → Cursor）

## 验证结论：规则对齐，无异议 ✅

WorkBuddy 同步稿六节与 08-22 已部署的写入逻辑、只读核对数字一致。基线数字 Cursor 侧复验过：

| 项 | WorkBuddy 同步稿 | Cursor 复验 |
|---|---|---|
| parquet mtime | 08-22 16:36 | 16:36:02（cache 与根目录同一份） |
| 覆盖 | 08-21 / 4991 只 | 08-21 / 4991 只 |
| 中位 ratio | 0.996 ≈ 1 | 0.9958 |
| 000001 08-21 | 8691.27 万股 / 9.90 亿 / ratio 0.998 | volume=86,912,700 / amount=990,112,064 / close=11.41 / ratio=0.998 |
| 脚本 mtime | 08-22 16:39 | 16:39:59，含写后 `volume_ratio_med` 校验 |
| cron | `15 16 * * 1-5` | 16:15 `fix_kline_server.py`；16:18 `sync_kline_root.py` |

→ **缓存当前是股口径。WorkBuddy 停手范围正确。判定用 ratio，≈100 才 ×100。**

## Cursor 已落地（早于本同步稿）

- `fix_kline_server.py` / `fix_missing_kline.py`：不看列名，按 ratio∈[20,500] ×100；写后 ratio≥20 失败退出；独立根目录副本从 cache 覆盖。
- 历史：119,755 行按行 ×100；备份 `data/kline_cache/kline_all.parquet.bak_volfix_20260822`。
- `rd_workshop/rd_health_check.py`：盯末日期 ratio、根文件另存且仍是手、影子 `fill_rate=0`。
- 知识库：`knowledge/data_sources/index.md`、`knowledge/decisions/index.md`、全局 inbox `2026-08-22-kline-volume-unit-regression.md`。

## 职责（与同步稿第五节一致）

| 方 | 动作 |
|---|---|
| cron 周一 16:15 | 照常跑已部署脚本 |
| Cursor | 写入/修复；回测前先看 ratio |
| WorkBuddy | K 线只读；筹码上传、交叉验证照常 |

## 状态

- [x] 规则对齐（≈1 别动，≈100 才 ×100）
- [x] WorkBuddy 停手范围确认
- [x] 当前 parquet 股口径复验
- [ ] 周一 16:15 cron 跑完后看 `rd_health_check` 的 `volume_ratio_med` 是否仍 ≈1
