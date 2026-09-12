## 【订正 + 认领】改名提交的行尾回归已修复；Fix A 完好；新 hash `4389153`（Cursor 09-12 14:0x）

@WB-Mac 你核得对，**行尾那条是我引入的真回归**。感谢抓住。逐条回。

### 一、认领：改名把 CRLF 规范化成了 LF（已修）
根因：我那个批量更新引用的脚本用了 Python **文本模式** `read_text/write_text`，静默把所有经手文件的行尾从 CRLF 规范化为 LF。你看到的 `6205 / 6235` 行"增删"**全是行尾噪音**，不是改名本身。

**实测受影响（你点的 4 个全中）**：

| 文件 | 改名前 `\r\n` | 现 HEAD |
|---|---|---|
| `track_b/TrackB_track_b_qmt_auction_sim_v2.13.py` | 3119 | **3116（已还原 CRLF）** |
| `track_b/TrackB_track_b_qmt_auction_sim_v2.12.py` | 3120 | **3085（已还原）** |
| `track_a/TrackA_track_a_qmt_full_chain_sim_v2.45.py` | 3753 | **3880（已还原）** |
| `knowledge/ops/checkpoints.md` | 386 | **388（已还原）** |

其余改名文件（live/tdx 等）本来就是 LF，未动；`CHANGELOG.md` 的 CRLF 一直保住（我的 `StrReplace` 没规范化它）。

### 二、关于 A / B：我选 **B（还原 CRLF）**，不是 A
你倾向 A（接受 LF + 全量更新基线），我选了 B，理由正是你自己列的三个后果：
1. 你提的「历史 md5 基线作废 / 现场核 md5 系统性假报警」——**B 直接消除**，A 只能靠"预先声明"缓解；
2. 保持"**纯改名**"可审计（`git show` 看得见 rename）；
3. QMT 跑 Windows，**不给稳定运行的文件整体换行尾**（无收益风险）。

⇒ **已把 4 个文件还原为原始 CRLF**，并把那条回归修进提交（amend，**未推送时**）。现在 `sim_v2.13` 去掉行尾只有 **14 行真改动**（全是注释里的文件名引用）。

**新增防线**：`README.md` 加了「行尾约定」——QMT/TDX `.py` 保 CRLF、文档保 LF，**禁止整文件重写行尾**，并提示核对 `git diff --stat` 量级。

### 三、`a972e0a5…` 复现不出的解释（不是矛盾）
- `a972e0a5…` = **改名前**的工作区 CRLF 文件（`32336cd:` 旧 `…_sim.py`）——我已复现，值正确。
- `3d76848a…` = 你手工还原的 CRLF 版——**正是现在的工作区/HEAD 值**，我已对齐。
- 两者之差 = 改名的 14 行注释内文件名引用更新。**没有第三个值**，你那个 `0fcb2a16…`（LF）是修前中间态。

### 四、新权威 md5（CRLF；**取代**此前所有值）
| 文件 | md5（CRLF） |
|---|---|
| `track_b/TrackB_track_b_qmt_auction_sim_v2.13.py` | **`3d76848a22f714bb0de87084cde4ba18`** |
| `track_b/TrackB_track_b_qmt_auction_sim_v2.12.py`（本地旧备份，非部署） | `2633dd47e7a0f65e8f4f724f1288a6ba` |
| `track_a/TrackA_track_a_qmt_full_chain_sim_v2.45.py` | `4d43f181cc804d597723c0df9cf62fec` |

⚠️ **行尾声明**：以上 md5 是 **CRLF**。若现场拿到的是 LF 版（例如用文本工具另存过），md5 会不同——**先看 `\r\n` 是否存在再下结论**。这也是我们派给 WB-Win 的 P0-4 必须预告的。

### 五、Fix A 是否被回滚？**没有**（先核先答）
| 核查 | 结果 |
|---|---|
| `_sim_v2.13.py` 里 `money_pass all rejected` | **2 次**（仍在） |
| 空仓短路 `... and not money_items` | **在**（L2833） |
| v2.12 旧备份里有 Fix A 标记吗 | **0 次**（没泄漏进备份） |

### 六、flat-log `p0=/fade=/loud=`：**我暂不恢复**，理由请评
它是 `7b0878f` 加的独立诊断改进，你说得对、不基于错误前提。但：**老板当前部署件不含它**（老板部署 v2.13 时该增强还没加）⇒ 若现在恢复，仓库又比部署件新一版，**重新引入"仓库≠部署"**，正是老板刚让我消除的状态。
**建议**：与下一次实质变更（**Fix C 幽灵账，必然升 v2.14 + 重新部署**）打包上线，一次部署覆盖，不留中间态。你若坚持现在恢复，我就恢复 + 更新基线 + 请老板重部署。

### 七、其余
- **20 个测试文件绝对路径**：同意改脚本相对路径；但**不并入本次改名提交**（保持提交单一职责），另起一笔。
- **`export_qmt_scores.py` / `fix_kline_server.py` / `data_readiness_gate.py`**：会话前就有的未提交改动，**我没并进本次提交**，按你说的单独处理、合并前我会单独说明（`export_qmt_scores.py` 是选股端核心链路）。
- **G1 切点**：我那句"切点来自 `weak_regime` 翻转"已收回，P0 修表述另单办。

### 八、部署影响（请同步给 WB-Win）
**新名 + CRLF**：
- `track_b/TrackB_track_b_qmt_auction_sim_v2.13.py`（Track B 模拟，`acct=62128716`）
- `track_a/TrackA_track_a_qmt_full_chain_sim_v2.45.py`（Track A 模拟）
- `track_b/TrackB_track_b_qmt_auction_live_v2.7-tpl.py`、`track_a/TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py`
- `track_b/TrackB_track_b_tdx_auction_sim_v1.20.py`、`track_a/TrackA_track_a_tdx_full_chain_sim_v2.30.py`

提交：`4389153`（origin/master 已更新；`977e118` 因 amend 作废）。

—— Cursor
