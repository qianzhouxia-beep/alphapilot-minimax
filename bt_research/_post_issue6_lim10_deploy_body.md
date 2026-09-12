## 【Fix A 部署确认】v2.13 已进 Windows QMT 模拟盘（Cursor 09-12 11:1x）

老板本机记事本已确认部署件含两个 v2.13 标记：`track-B v2.13`、`money_pass all rejected -> flat`（记事本不改行尾，可确认内容一致）。

**关于放行条件 ①（行级 diff/hash）的处理**：老板已部署覆盖，**改前 md5 已不可取**；改为**核对改后值**（同目的：证明运行副本 = 仓库副本）：

| 项 | 值 |
|---|---|
| 仓库副本 md5（CRLF，Windows 行尾） | `1da96de8636cb9b5f014bda1ad8812ef` |
| 仓库副本 sha1（CRLF） | `6b68557b9189a4ffe644c228c8856b06cd3368ae` |
| 若行尾被转为 LF | md5 = `4f65bdd9445d6707e6d4722beace3211`（内容等价） |

**周一日志验收（与你 §三/§五 的口径一致）**：
1. 首行应为 `[INIT] track-B v2.13 (LIM10-failsafe+LIM10+path_fade+loud_vol+R5+call-shadow) | acct=...`；
2. 若当日资金门全灭（`money_flow_pass` 全 False）应有 `[LIM10] money_pass all rejected -> flat (no fallback) other=N` 且**买入 0 笔**——旧版此处必现误导串 `no limit_cnt_10d on pool -> FCFS fallback` 并买入被否决票；
3. sim 满 1 日核对无异常前不进 live。

**状态**：Fix A 闭环（仓库 `fe8f751` → 部署 → 待周一日志）。**Fix C 仍未做**，按授权需独立 ticket/commit，等点名。

—— Cursor
