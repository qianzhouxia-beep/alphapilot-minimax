# 给 qcloud：板块研报入口 + 浅色风格统一

> 目标域名：`https://alphapilot.api-tokenmaster.com`  
> 看板页：`/cn/sectors/`（浅色，已上线）  
> 研报页：`/cn/sectors/research/{date}/{session}/`（现为黑底，需统一）  
> 透传：Zeabur 网关已把 `/cn/sectors/research/*` → 上海 `/api/v1/cn/sectors/research/*`（公网 200 已通）

---

## 背景（不必重做）

- 研报由上海 `sector_research_report.py` 生成静态 HTML（含 ECharts），路径：
  ```text
  /home/ubuntu/alphapilot/output/sector_research/
  ├── index.html
  └── {date}/{session}/index.html
  ```
- 公网漂亮路径已可打开；**缺的是看板入口 + 视觉与主站统一**。
- **不要**把 HTML push 进 GitHub/`public/`。
- **不要**用 React 重写整页 ECharts。
- **不要**改 Cloudflare 把整站指到上海（除非另开子域名且已确认）。

---

## 任务一：看板加入口（前端，仓库 `alphapilot-minimax`）

文件：`frontend/app/cn/sectors/page.tsx`（标题区约 316–333 行）

在「板块研报」标题旁 / 「刷新数据」按钮旁，增加入口按钮或链接：

```tsx
<a
  href="/cn/sectors/research/"
  className="rounded-xl border border-border-subtle bg-bg-secondary px-4 py-2 text-[13px] font-medium text-text-primary hover:border-purple-primary/40"
>
  深度研报归档
</a>
```

要求：
- 文案可用：「深度研报」或「盘后/盘中研报归档」
- 风格与现有「刷新数据」按钮一致（浅色、圆角、细边框）
- 点击进入 `/cn/sectors/research/`（已透传，勿链到 `/api/v1/...`）
- 可选：若今日已有 `afternoon`/`morning`，再加「今日研报」直达链接

若你改不了 Zeabur 前端仓库，回复「前端入口待 Cursor」，并继续做任务二（HTML 换肤）。

---

## 任务二：研报 HTML 换肤（上海，必须）

改脚本：`/home/ubuntu/alphapilot/sector_research_report.py`  
同时改归档页与单日研报页的内联 CSS（含 `index.html` 生成逻辑）。

### 问题

当前研报是**黑底**：

```css
--bg: #0f1117; --card: #1a1d28; --border: #2a2e3a;
--text: #e5e7eb; --purple: #8b5cf6;
```

主站 `/cn/sectors/` 是**浅色 Apple 风**（见 `frontend/app/globals.css`）。

### 必须对齐的 Design Tokens

```css
:root {
  --bg: #F5F5F7;           /* bg-primary */
  --card: #FFFFFF;         /* bg-secondary / card */
  --bg-tertiary: #FAFAFA;
  --border: rgba(0,0,0,0.06);
  --text: #1D1D1F;
  --text-secondary: #3A3A40;
  --text-tertiary: #55555B;
  --purple: #7C5CFC;       /* 主站紫，不要用 #8b5cf6 */
  --purple-light: #EDE9FE;
  --red: #FF3B30;          /* 流入（A股习惯红涨/红流入） */
  --green: #34C759;        /* 流出 */
  --radius: 16px;          /* 卡片圆角偏大 */
  --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
```

### 布局与组件（对齐看板，而不是另做一套暗黑仪表盘）

1. **页面底**：浅灰 `#F5F5F7`，不要纯黑。  
2. **卡片**：白底 + 细边框 + 轻阴影 + `border-radius: 16px~20px`。  
3. **顶栏**：
   - 返回链：`← 返回板块看板` → `/cn/sectors/`
   - 可选第二链：`研报归档` → `/cn/sectors/research/`
   - 标题层级接近看板：主标题约 26–28px、`font-weight: 700`；副标题 13px 灰色。  
4. **不要**：紫色大面积渐变背景、霓虹 glow、过黑 card、默认 Inter 堆砌感过重的暗色仪表盘。  
5. **ECharts**：
   - `backgroundColor: 'transparent'`
   - 坐标轴/文字：`#3A3A40` / `#55555B`
   - 分割线：`rgba(0,0,0,0.06)`
   - 流入红 `#FF3B30`，流出绿 `#34C759`
   - tooltip：白底深字  
6. **归档列表**（`output/sector_research/index.html`）：
   - 同样浅色 token  
   - 日期行用白卡片，session 用描边小按钮（紫边紫字，hover 浅紫底）  
   - 去掉黑底紫描边「游戏感」按钮  

### 生成后自检

```bash
# 重新生成今日 afternoon + 索引
cd /home/ubuntu/alphapilot
python3 -u sector_research_report.py --session afternoon

# 本机 API
curl -s http://127.0.0.1:8000/api/v1/cn/sectors/research/ | head
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" \
  http://127.0.0.1:8000/api/v1/cn/sectors/research/2026-07-20/afternoon/
```

公网（透传已通）：

- https://alphapilot.api-tokenmaster.com/cn/sectors/research/
- https://alphapilot.api-tokenmaster.com/cn/sectors/research/2026-07-20/afternoon/

用浏览器打开：应是**浅色**，图表可读，无黑底。

---

## 任务三：Cron（若尚未对齐）

```cron
# 板块研报
35 11 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u sector_research_report.py --session morning >> output/logs/sector_research.log 2>&1
5 15 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u sector_research_report.py --session afternoon >> output/logs/sector_research.log 2>&1
```

每次跑完必须刷新归档 `output/sector_research/index.html`。

---

## 交付回复请包含

1. 是否已改 `sector_research_report.py` 浅色 token（贴关键 CSS `:root` 片段）  
2. 是否已在 `/cn/sectors/` 加「深度研报归档」入口；若否写「前端待 Cursor」  
3. 公网索引 + 今日研报两个 URL（浅色截图或说明）  
4. crontab 两行原文  

## 不要做

- 不要 push 研报 HTML 进 GitHub  
- 不要改 Cloudflare 整站指到上海  
- 不要保留黑底研报作为默认主题  
- 不要引入新的整站暗黑模式  

---

## Cursor 可补（若 qcloud 只做上海）

- `frontend/app/cn/sectors/page.tsx` 增加「深度研报归档」按钮 → `/cn/sectors/research/`  
- 按钮 class 对齐现有「刷新数据」  
