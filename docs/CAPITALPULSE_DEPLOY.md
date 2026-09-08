# CapitalPulse 资金流看板 — 集成与部署说明

> 将开源项目 [CapitalPulse](https://github.com/liuqingxi23/CapitalPulse)（行业/个股资金流实时看板）深度集成进 AlphaPilot：
> 后端服务挂载到现有 FastAPI（`run_server.py`），前端页面接入现有 Next.js（`/cn/funds`）。

---

## 一、集成了什么

| 层 | 位置 | 说明 |
| --- | --- | --- |
| 后端包 | `capitalpulse/` | 采集服务（板块/个股资金流）、SQLite 持久化、REST + WebSocket |
| 挂载点 | `run_server.py` | `bridge.setup(app)` 统一挂载路由 / WS / 生命周期 |
| 前端页面 | `_fe_verify/frontend/app/cn/funds/page.tsx` | 实时看板（主力/超大单/大单/中单/小单 + 30 日柱状 + 个股秒级） |
| 导航入口 | `components/HeaderBar.tsx` | 新增「资金 → 资金流向看板」 |
| 依赖 | `package.json` | 新增 `echarts`、`lucide-react` |

### 后端路由一览（前缀 `/api/v1/finance`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sector-flow/history` | 当日板块主力资金快照 + 全天曲线（`top=10/30`） |
| GET | `/sector-flow/detail-history` | 六大细分资金曲线（分页，每页 6 行业） |
| GET | `/sector-flow/daily-history` | 30 日日频主力净流入（`top=30&days=30`） |
| GET | `/sector-flow/status` | 采集服务运行状态 |
| GET | `/stock-flow/session` | 个股模式会话（默认标的等） |
| GET | `/stock-flow/search` | 东财个股搜索（代码/名称/拼音） |
| GET | `/stock-flow/history` | 个股当日分钟级资金历史 |
| WS | `/ws/sector-flow` | 板块资金实时推送（3 秒轮询东财） |
| WS | `/ws/stock-flow` | 个股资金实时推送（`?quote_id=&code=&name=`） |

### 采集行为
- 启动时自动启动两个采集服务，收盘后自动降频、开盘自动恢复；
- 数据落在 `data/sector_flow_realtime.sqlite3`（可通过 `SECTOR_FLOW_DB_PATH` 覆盖）；
- 上游为东财实时接口，主通道超时自动切 `push2delay` 备用通道；
- 启动时若当日无快照会自动回填开盘至今的历史分钟数据。

---

## 二、本地联调

```bash
# 1) 后端（独立调试入口，无需完整 api_server）
cd C:\Users\elvisq\Projects\alphapilot
$env:PYTHONUTF8=1; python -m uvicorn capitalpulse.standalone:app --host 0.0.0.0 --port 8000

# 2) 前端（另开终端）
cd _fe_verify\frontend
npm install          # 已加入 echarts / lucide-react
npm run dev          # http://localhost:3000/cn/funds
```

> 前端默认同源请求 `/api/v1/finance/*` 与 `/ws/*`。
> 若前后端端口不同，可用 `NEXT_PUBLIC_SECTOR_FLOW_WS_URL` 指定 WS 地址；
> 生产环境无需额外配置（同源）。

### 已验证
- `GET /api/v1/finance/sector-flow/{status,history}` → 200（含 30 行业快照、7200 点回填）
- `GET /api/v1/finance/sector-flow/daily-history` → 200（东财 30 日真实数据，`failed=0`）
- `WS /ws/sector-flow`、`/ws/stock-flow` → snapshot 正常
- `next build` 通过，`/cn/funds` 路由生成

---

## 三、生产部署（腾讯云 150.158.100.236 + Zeabur）

### 1. 后端部署（腾讯云）

把代码同步到服务器后重启 API 服务：

```bash
cd /home/ubuntu/alphapilot
git pull            # 或按既有方式同步 capitalpulse/ 与 run_server.py
sudo systemctl restart alphapilot-api
```

启动日志应出现：

```
[capitalpulse] starting collectors...
[capitalpulse] stopping collectors...   # 停止时
```

验证：

```bash
curl -s http://127.0.0.1:8000/api/v1/finance/sector-flow/status
# → {"code":200,"msg":"success","data":{"enabled":true,"market_status":...,"selected_count":30,...}}
```

> 服务依赖 `run_server.py`（生产入口，已挂 `bridge.setup`）。
> 若服务器用别的启动命令（如 `_srv_run_server.py`），同样补一行
> `from capitalpulse import bridge; bridge.setup(app)` 即可。

### 2. 前端构建与部署

```bash
cd _fe_verify/frontend
npm ci
npm run build
# 产物 out/ 或 standalone —— 按既有 frontend_out 流程上传到
# /home/ubuntu/alphapilot/frontend_out/
```

> `api_server.py` 已把 `/cn` 挂载为静态目录，新页面即 `/cn/funds`。

### 3. 代理层（Zeabur）

现有链路 `Zeabur HTTPS → cn_proxy.py → 腾讯云`。
`cn_proxy.py`（在 Zeabur 侧，不在本仓库）需新增两条规则，**否则页面能打开但拉不到数据**：

- 转发 `GET /api/v1/finance/*` → 腾讯云 `http://150.158.100.236/api/v1/finance/*`
- 转发 `WS /ws/*` → 腾讯云 `ws://150.158.100.236/ws/*`（必须透传 `Upgrade` / `Connection: Upgrade` 头）

如果走 Nginx，同样需要为 `/ws/` 配置：

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### 4. 可选环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SECTOR_FLOW_ENABLED` | `1` | 设为 `0` 关闭板块采集 |
| `SECTOR_FLOW_POLL_SECONDS` | 3 | 板块采集轮询间隔（秒） |
| `STOCK_FLOW_POLL_SECONDS` | 3 | 个股采集轮询间隔（秒） |
| `SECTOR_FLOW_DB_PATH` | `data/sector_flow_realtime.sqlite3` | SQLite 路径 |
| `SECTOR_FLOW_RETENTION_DAYS` | 7 | 历史快照保留天数 |

---

## 四、故障排查

| 现象 | 排查 |
| --- | --- |
| 页面打开但曲线空白 | 看 `/sector-flow/status` 的 `market_status`；休市时无盘中数据是正常的 |
| 接口 503 `not ready` | 采集服务启动中/被 `SECTOR_FLOW_ENABLED=0` 关闭 |
| WS 连不上 | 确认代理层透传 Upgrade 头；浏览器看 Network → WS 帧 |
| 东财主通道超时 | 服务会自动切 `push2delay` 备用通道，日志有 `Request error ... (attempt 2/2)` 属正常重试 |

---

## 五、代码结构速览

```
capitalpulse/
├── __init__.py
├── bridge.py            # 挂载入口：路由 + WS + startup/shutdown
├── standalone.py        # 本地独立调试入口
├── config.py            # 东财 URL / 超时 / DB 路径
├── routers/__init__.py
├── services/
│   ├── sector_flow_upstream.py   # 东财板块数据抓取
│   ├── stock_flow_upstream.py    # 东财个股数据抓取 + 搜索
│   ├── sector_flow_realtime.py   # 板块采集服务 + SQLite + WS 广播
│   └── stock_flow_realtime.py    # 个股采集服务 + SQLite + WS 广播
└── utils/
    ├── http_client.py            # httpx 重试/超时/GBK 解码
    └── sector_selection.py       # 申万二级行业筛选
```
