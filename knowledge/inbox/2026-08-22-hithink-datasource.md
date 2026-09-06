---
project: alphapilot
domain: data
title: 同花顺官方 API 已写入数据源档案，以后可按需调用
date: 2026-08-22
status: decision
tags: [同花顺, hithink, fuyao, 数据源]
source_chat: 同花顺数据源入库
---

# 同花顺官方数据源已建档

## 结论（2-3 句）

HiThink / Fuyao（`https://fuyao.aicubes.cn`）作为 AlphaPilot 的**缺口源**写入知识库：涨停/跌停/炸板、连板、热股、龙虎榜、竞价、异动。不替换主 K 线与 09:35 打分。生产排序暂不加（已回测否决）。以后要用：读 `knowledge/data_sources/hithink.md`，对话走 `user-fuyao-*` MCP，脚本走 REST + 本地/服务器 Key。

## 证据

- 档案：`alphapilot/knowledge/data_sources/hithink.md`
- Key：服务器 `config/hithink_api_key.conf`（0600）或 `~/.hithink_finance_api_key`，不进 git
- 落地：15:40 `scripts/hithink_overlay.py`；09:35 `hithink_p2_side.py` 默认只标注
- 排序否决见 `knowledge/signals/hithink_p2_t1.md`

## 影响 / 下一步

- Agent 需要涨停原因、连板、官方热股/龙虎榜、竞价快照时走此源
- 再接入选股必须 as-of 回测通过
- 分钟 K / L2 / 外盘仍不走此源

## 关联

- `knowledge/data_sources/hithink.md`
- `knowledge/data_sources/index.md`
