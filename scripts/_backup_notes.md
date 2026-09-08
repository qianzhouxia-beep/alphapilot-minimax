# AlphaPilot 备份说明（2026-08-29）

> 本地仓库 → 上海中转 → 新加坡备份。因用户本地屏幕异常，为防数据丢失而做的异地备份。

## 备份位置

```
/home/ubuntu/alphapilot/backups/
├── backup_alphapilot_20260829.tar.gz   # 原始打包 (354.6MB, MD5=0137de852ee45247311ef373cee26327)
└── extracted/                          # 已解压内容 (642M)
```

## 备份内容（本地仓库权威版本）

| 目录 | 内容 |
|---|---|
| `models/` | 全部模型：v25 生产三模型 + meta；v26 5m/daily 实验三模型 + walkforward；v27/v28 walkforward；extra_factors.parquet 等 |
| `production_strategies/` | 轨道 A/B 全部生产策略代码（唯一权威来源）+ CHANGELOG + 文档 |
| `knowledge/` | 知识库（INDEX / models / strategies / signals / decisions / data_sources / ops 等） |
| `docs/` | 全部设计文档、研究结论、交接单、PDF/HTML 报告 |
| `scripts/` | 服务器/本地脚本 |
| `bt_research/` | 回测研究代码与结论 |
| `research/` `crypto/` `data/` | 研究数据、加密项目、关键数据 |
| 根文件 | AGENTS.md / CONTEXT-MAP.md / MEMORY.md / README.md |

## 变更记录（2026-08-29）

- **旧模型已删除**：`/home/ubuntu/alphapilot/models/`（2026-07-17 旧 v25 + v25b 废弃实验版）已按用户要求删除，防止与最新模型混淆。
- **新模型权威**：当前生产模型是本地 2026-08-28 的 `v25_opt_ensemble_{1,2,3}.ubj`（已含在备份中）。
- 上海临时中转文件已清理。

## 恢复方法

```bash
# 如需恢复
cd /home/ubuntu/alphapilot
tar -xzf backups/backup_alphapilot_20260829.tar.gz   # 覆盖对应目录
# 或使用已解压的 extracted/ 直接复制
cp -r backups/extracted/models models
```
