# AlphaPilot 迁机移交清单 · PC → MacBook

> 日期：2026-09-05  
> 原则：**本机 PC 原样保留，不删除；Mac 是另一套工作副本，按需同步。**  
> 远程仓库：`https://github.com/qianzhouxia-beep/alphapilot-minimax.git`（当前分支 `master`）  
> 生产服务器：仍是 `/home/ubuntu/alphapilot`（管线/cron 不动；迁 Mac ≠ 迁生产）

---

## 0. 先对齐预期（读这一段就够定调）

| 问题 | 答案 |
|---|---|
| PC 上那 5 万条 uncommitted 要清掉吗？ | **不用删。** 多半是 `node_modules` / `.next` / 大 CSV / 缓存。PC 继续留着不影响 Mac。 |
| 必须用 Cursor Cloud 吗？ | **不必。** Cloud 是临时 Agent VM，不是把项目「搬」到 Mac。迁机走 Git + 可选拷贝。 |
| Mac 能替代 QMT 实盘吗？ | **不能。** QMT / 通达信交易端仍在 Windows。Mac 适合研发、回测、看报告、改代码。 |
| 两边会不会冲突？ | **路径不同就基本不冲突。** 各改各的工作区；用 Git 合流代码；大数据各留各的或从服务器再拉。 |

---

## 1. 三类东西：带 / 可选带 / 别带

### A. 应该经 Git 带到 Mac（源码真相）

提交并 `git push` 后再在 Mac `clone` / `pull`：

- 策略与生产归档：`production_strategies/`
- 管线与核心脚本：`alphapilot_pipeline_v3.py`、`recommend.py`、`vm25_scorer.py`、`morning_live_fund_select.py`、`trade_executor.py`、`api_server.py` 等
- 知识库：`knowledge/`（含 `ops/checkpoints.md`）
- 研发：`bt_research/`（**脚本**）、`rd_workshop/`、`scripts/`
- 前端源码：`frontend/`（只要源码，不要 `node_modules` / `.next`）
- 文档：`docs/`、`AGENTS.md`、`MEMORY.md`、`DESIGN.md`、`tokens.css`
- 配置模板：`.env.example` / `config/*.example`（若有）；**不要提交真实密钥**

### B. 可选拷贝（体积大，PC 可留着，Mac 需要再拷或从服务器拉）

用移动硬盘 / `scp` / 网盘；**不必从 Git 走**：

| 内容 | 大约用途 | 建议 |
|---|---|---|
| `data/kline_cache/*.parquet` | 本地回测 K 线 | Mac 优先从**服务器**再拉一份，避免拷坏/拷旧 |
| `data/fund_flow_history*.json` | 资金流 | 同上，或按需拷最近一份 |
| `output/` 里**你还要看的报告** | 如 `bt_port_100k_top2_t1close_report.pdf` | 只拷少数成品，别整目录（内含 GB 级 CSV） |
| `models/*.ubj` 等 | 本地推理 | 若 Mac 要跑打分，从服务器 `models/` 同步 |
| 个人笔记、截图、PDF 草稿 | 阅读 | 随意拷，与 Git 无关 |

### C. 留在 PC，不要指望 Mac 自动有

- QMT / 通达信策略部署目录、交易账号环境
- 本机实盘状态（若在 `C:\alphapilot\` 一类路径）：`live_pos_state.json`、成交账本等
- `_fe_verify/`、`marketing_video/node_modules`、`.next`、巨型 `output/*.csv`、备份 `*.tar.gz`
- 根目录大量 `_tmp_*` / `_smoke_*` 一次性脚本（PC 留档即可）
- 真实 `.env`、API Key、微信机器人密钥

---

## 2. PC 侧：出发前 Checklist（不删本地）

- [ ] **取消** Cursor「Include uncommitted changes / Continue on Cloud」——迁机不靠它
- [ ] 确认远程：`git remote -v` → `qianzhouxia-beep/alphapilot-minimax`
- [ ] （强烈建议）补一份 `.gitignore`（只忽略垃圾，**不删除磁盘文件**），让以后 `git status` 清爽  
  建议忽略：`node_modules/`、`.next/`、`__pycache__/`、`*.pyc`、`_fe_verify/`、`output/*.csv`、`output/*.parquet`、`*.tar.gz`、大缓存 parquet 等
- [ ] 挑真正要带走的源码改动，**小批量 commit + push**（不要一次把 5 万文件塞进去）  
  若暂不想整理提交：Mac 可先 `clone` 远程已有 `master`，本地未推改动之后再挑着同步
- [ ] 列一份「Mac 第一天就要看的文件」短名单（例：某份 PDF 报告、某篇 knowledge 卡）→ 单独拷贝
- [ ] 记下服务器访问方式（SSH 主机/用户）——Mac 拉数据用，**密钥只存在本机钥匙串，不要写进仓库**

---

## 3. Mac 侧：落地 Checklist

- [ ] 安装：Git、Python 3.x（与服务器接近更佳）、Node（若要跑前端）
- [ ] `git clone https://github.com/qianzhouxia-beep/alphapilot-minimax.git`
- [ ] 建虚拟环境并装依赖（按仓库 `requirements*.txt` / `pyproject`；没有就对照服务器 `pip freeze` 精简装）
- [ ] 前端若需要：`cd frontend && npm i`（**在 Mac 本地装**，不要从 PC 拷 `node_modules`）
- [ ] 需要回测时再：从服务器 `scp`/`rsync` `data/kline_cache`、必要 `models/`
- [ ] Cursor 打开 Mac 上的仓库目录；Agent 选 **This Mac / This PC**，不要默认 Cloud
- [ ] 跑一个烟雾：`python -c "import recommend"` 或打开已有报告 PDF 确认环境

---

## 4. 日常双机怎么共存（避免打架）

1. **代码**：只通过 Git 合流；同一功能尽量在一台机改完再 push。  
2. **数据**：Mac / PC 各自缓存；以**服务器**为权威数据源，过期就重拉。  
3. **生产策略**：改 `production_strategies/` → CHANGELOG → 你手动部署到交易端（规则不变）。  
4. **实盘**：只在 Windows + QMT；Mac 不做下单。  
5. **PC 磁盘**：继续当「重型回测 / 历史垃圾堆 / 交易旁路」；不着急清理。

---

## 5. 第一周最小可行（MVP）

若只想尽快在 Mac 上「能打开项目、能改代码、能看文档」：

1. Mac：`git clone` + 装 Python  
2. 打开 `knowledge/INDEX.md`、`AGENTS.md`  
3. 需要时再拉 `data/` / `models/`  
4. PC：一切保留，继续跑 QMT  

「完整回测环境」可以第二周再补数据，不必第一天拷 2GB+ 缓存。

---

## 6. 明确不做的事

- 不要点 Cloud 的 **Include Changes** 指望迁机  
- 不要 `git add` 整个 `_fe_verify` / `node_modules` / GB 级 `output`  
- 不要删 PC 工作区「为了迁机」——清单目标是**复制/同步，不是搬家清空**  
- 不要以为 Mac 上 clone 完就等于生产已迁移——生产仍在服务器 + Windows 交易端

---

## 7. 相关路径速查

| 角色 | 路径 |
|---|---|
| 本机仓库（PC） | `C:\Users\elvisq\Projects\alphapilot` |
| GitHub | `qianzhouxia-beep/alphapilot-minimax` |
| 生产服务器（上海） | `/home/ubuntu/alphapilot`（主机见运维约定，勿与新加坡备份站混淆） |
| **新加坡异地备份（已核实 2026-09-05 仍在）** | `ubuntu@43.156.119.47:/home/ubuntu/alphapilot/backups/` |
| 备份包 | `backup_alphapilot_20260829.tar.gz`（355MB，MD5=`0137de852ee45247311ef373cee26327`） |
| 备份已解压 | `backups/extracted/`（约 642MB：models / production_strategies / knowledge / docs / scripts / bt_research / crypto / data …） |
| 策略权威 | `production_strategies/` |
| 近期组合回测报告 | `output/bt_port_100k_top2_t1close_report.pdf` |
| PDF 导出脚本 | `scripts/html_to_pdf.py` |

### 7.1 从新加坡备份拉到 Mac（可选，快于整盘拷 PC）

备份截止 **2026-08-29**，比今天的本地工作区旧约一周；适合「先有一套完整代码+模型骨架」。  
08-29 之后的改动仍要用 **GitHub pull** 或 PC 上挑文件补。

```bash
# 在 Mac 上（需已配置 SSH 到新加坡；密码见本机 scripts/_backup_upload_sg.py，勿写进仓库新文件）
scp ubuntu@43.156.119.47:/home/ubuntu/alphapilot/backups/backup_alphapilot_20260829.tar.gz .
mkdir -p ~/alphapilot && tar -xzf backup_alphapilot_20260829.tar.gz -C ~/alphapilot
# 然后再: git remote add / git pull 对齐 GitHub 更新
```

**注意**：新加坡机器同时也跑加密纸盘等，目录 `/home/ubuntu/alphapilot/` 不全是「纯备份」；迁机请优先用 `backups/` 里的包或 `extracted/`，不要误把整台 SG 当生产 A 股源。

---

## 8. 下一步（你点头我再动手）

可选，**都不强制删文件**：

1. 写好 `.gitignore`（忽略垃圾，磁盘原样保留）  
2. 帮你列「值得先 commit 的已修改源码」短名单（那 69 个 modified 里挑）  
3. 写一段 Mac 用的「从服务器拉 K 线/模型」命令模板  

当前会话结论：迁 Mac = **Git 同步代码 + 按需拷/拉数据**；PC 可完整保留。
