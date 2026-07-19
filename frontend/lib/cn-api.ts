// AlphaPilot A 股后端 API 统一封装
// 2026-07-09: 添加收藏追踪 API
// 2026-07-13: 添加 /recommend/live 实时资金流 API

// 同源代理: Zeabur HTTPS -> cn_proxy.py -> 腾讯云 150.158.100.236
// 本地开发: 直连 Zeabur 生产站（CORS已开放 *）
const CN_API_BASE =
  typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "https://alphapilot.api-tokenmaster.com"
    : "";

// 端点（本地开发时自动加 Zeabur base，生产环境用同源路径）
function endpoint(path: string) {
  return `${CN_API_BASE}${path}`;
}

export const CN_ENDPOINTS = {
  recommend: endpoint(`/api/v1/cn/recommend`),
  search: endpoint(`/api/v1/cn/search`),
  marketOverview: endpoint(`/api/v1/cn/market-overview`),
  indices: endpoint(`/api/v1/cn/indices`),
  pipelineRun: endpoint(`/api/v1/cn/pipeline/run`),
  chat: endpoint(`/api/v1/cn/chat`),
  deepReport: endpoint(`/api/v1/cn/deep-report`),
  backtest: endpoint(`/api/v1/cn/backtest`),
  news: endpoint(`/api/v1/cn/news`),
  watchlist: endpoint(`/api/v1/cn/watchlist`),
  recommendCategorized: endpoint(`/api/v1/cn/recommend/categorized`),
  recommendEOD: endpoint(`/api/v1/cn/recommend/eod`),
  recommendLive: endpoint(`/api/v1/cn/recommend/live`),
} as const;

// 类型定义
export type ScreenerItem = {
  symbol: string;
  name: string;
  score: number;
  lgb_score: number;
  sector_heat: number;
  buy_price: number;
  target_price: number;
  stop_price: number;
  active_buy_ratio?: number | null;
  turnover?: number | null;
  volume_ratio?: number | null;
  money_flow_pass?: boolean | null;
  score_raw?: number | null;
  net_profit?: number | null;
  eps?: number | null;
  roe?: number | null;
  revenue?: number | null;
  fundamental_pass?: boolean | null;
  industry_code?: number | null;
  sector?: string | null;
  sector_change_pct?: number | null;
  money_phase?: string | null;
  money_phase_label?: string | null;
  score_label?: string | null;
  score_rank_pct?: number | null;
  change_pct?: number | null;
};

export type RecommendStats = {
  total_scanned: number;
  valid_scored: number;
  elapsed_seconds: number;
  returned: number;
  filtered_out: number;
};

export type IndexData = {
  name: string;
  code: string;
  price: number;
  change: number;
  change_pct: number;
  open: number;
  high: number;
  low: number;
  prev_close: number;
};

export type IndicesResponse = {
  indices: IndexData[];
  count: number;
};

export type ScreenerResponse = {
  run_at: string;
  recommendations: ScreenerItem[];
  stats: RecommendStats;
};

export type MarketOverview = {
  total_stocks: number;
  up_count: number;
  down_count: number;
  sector_count: number;
};

export type SearchResult = {
  symbol: string;
  name: string;
  sector: string | null;
  score: number | null;
  main_force: string | null;
};

export type AgentVote = {
  agent: string;
  vote: "赞同" | "反对" | "中性";
  reason: string;
  color?: string;
};

export type ChatResponse = {
  content: string;
  stock: {
    symbol: string;
    name: string;
    score: number;
    price?: number;
    change_pct?: number;
  } | null;
  agent_results: AgentVote[] | null;
  llm_enabled?: boolean;
};

export type BacktestItem = {
  symbol: string;
  name: string;
  score: number;
  entry_date?: string;
  exit_date?: string;
  entry_price?: number;
  exit_price?: number;
  return: number | null;
  win: boolean | null;
  note?: string;
};

export type BacktestKpi = {
  avg_return: number;
  win_rate: number;
  max_return: number;
  min_return: number;
  positive_count: number;
  negative_count: number;
  total_scored: number;
  valid: number;
};

export type BacktestResponse = {
  total: number;
  results: BacktestItem[];
  kpi: BacktestKpi;
  config?: {
    startDate: string;
    endDate: string;
    holdingDays: number;
    topN: number;
    minScore: number;
  };
  note?: string;
};

export type WatchlistItem = {
  id: number;
  symbol: string;
  name: string;
  sector?: string | null;
  sector_change_pct?: number | null;
  added_at: string;
  entry_price: number;
  model_score: number;
  current_price?: number | null;
  current_change_pct?: number | null;
  day1_price: number | null;
  day1_change: number | null;
  day1_date: string | null;
  day2_price: number | null;
  day2_change: number | null;
  day2_date: string | null;
  day3_price: number | null;
  day3_change: number | null;
  day3_date: string | null;
  status: string;
  notes: string;
};

export type WatchlistResponse = {
  watchlist: WatchlistItem[];
  count: number;
};

// 统一 fetch 封装
async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Backend ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json();
}

// 业务函数
export async function fetchCNScreener(): Promise<ScreenerResponse> {
  return apiFetch<ScreenerResponse>(CN_ENDPOINTS.recommend);
}

export async function fetchCNMarketOverview(): Promise<MarketOverview> {
  return apiFetch<MarketOverview>(CN_ENDPOINTS.marketOverview);
}

export async function fetchCNIndices(): Promise<IndicesResponse> {
  return apiFetch<IndicesResponse>(CN_ENDPOINTS.indices);
}

export async function searchCNStocks(keyword: string): Promise<SearchResult[]> {
  return apiFetch<SearchResult[]>(`${CN_ENDPOINTS.search}?keyword=${encodeURIComponent(keyword)}`);
}

export async function triggerCNPipeline(): Promise<{ status: string; [k: string]: any }> {
  return apiFetch(CN_ENDPOINTS.pipelineRun, { method: "POST" });
}

export async function postCNChat(question: string): Promise<ChatResponse> {
  return apiFetch<ChatResponse>(`${CN_ENDPOINTS.chat}?question=${encodeURIComponent(question)}`);
}

/** 深度研报：异步任务 */
export type DeepReportJob = {
  job_id: string;
  symbol: string;
  name?: string;
  status: "queued" | "running" | "done" | "error" | string;
  progress?: string;
  decision?: string | null;
  report_markdown?: string | null;
  engine?: string;
  error?: string;
  created_at?: string;
  finished_at?: string;
  elapsed_seconds?: number;
  trade_date?: string | null;
};

export type DeepReportListItem = {
  job_id: string;
  symbol?: string;
  name?: string;
  status?: string;
  decision?: string | null;
  created_at?: string;
  finished_at?: string;
  engine?: string;
};

export async function startDeepReport(
  symbol: string,
  opts?: { trade_date?: string; engine?: string }
): Promise<{ job_id: string; symbol: string; name?: string; status: string }> {
  return apiFetch(CN_ENDPOINTS.deepReport, {
    method: "POST",
    body: JSON.stringify({
      symbol,
      trade_date: opts?.trade_date,
      engine: opts?.engine || "auto",
    }),
  });
}

export async function getDeepReport(jobId: string): Promise<DeepReportJob> {
  return apiFetch<DeepReportJob>(`${CN_ENDPOINTS.deepReport}/${encodeURIComponent(jobId)}`);
}

export async function listDeepReports(limit = 20): Promise<{ items: DeepReportListItem[] }> {
  return apiFetch(`${CN_ENDPOINTS.deepReport}?limit=${limit}`);
}

export async function postCNBacktest(cfg: {
  startDate: string;
  endDate: string;
  holdingDays: number;
  topN: number;
  minScore: number;
}): Promise<BacktestResponse> {
  return apiFetch<BacktestResponse>(CN_ENDPOINTS.backtest, {
    method: "POST",
    body: JSON.stringify(cfg),
  });
}

// 实时资金流（每60秒轮询，盘中阶段标签实时刷新）
export type LiveRecommendItem = ScreenerItem & {
  main_inflow?: number;
  main_outflow?: number;
  main_net?: number;
  _data_source?: "live" | "daily_recommend";
};

export type LiveRecommendResponse = {
  ts: number;
  fetch_ms: number;
  count: number;
  data: LiveRecommendItem[];
  rerank?: boolean;
};

export async function fetchLiveRecommend(top_n: number = 50, rerank: boolean = false): Promise<LiveRecommendResponse> {
  const params = rerank ? `?top_n=${top_n}&rerank=true` : `?top_n=${top_n}`;
  return apiFetch<LiveRecommendResponse>(`${CN_ENDPOINTS.recommendLive}${params}`);
}

// 尾盘选股
export async function fetchEODRecommend(): Promise<{ recommendations: any[]; note: string; run_at: string }> {
  return apiFetch(CN_ENDPOINTS.recommendEOD);
}

// 收藏追踪 API
export async function fetchWatchlist(): Promise<WatchlistResponse> {
  return apiFetch<WatchlistResponse>(CN_ENDPOINTS.watchlist);
}

export async function addToWatchlist(symbol: string, name: string, entry_price: number, model_score: number): Promise<any> {
  return apiFetch(CN_ENDPOINTS.watchlist, {
    method: "POST",
    body: JSON.stringify({ symbol, name, entry_price, model_score }),
  });
}

export async function removeFromWatchlist(symbol: string): Promise<any> {
  return apiFetch(`${CN_ENDPOINTS.watchlist}/${symbol}`, { method: "DELETE" });
}

export async function updateWatchlistEntry(symbol: string, data: { entry_price?: number; notes?: string }): Promise<any> {
  return apiFetch(`${CN_ENDPOINTS.watchlist}/${symbol}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ════════════════════════════════════════
// 分类推荐 API
// ════════════════════════════════════════

export type CategorizedStock = {
  symbol: string;
  name: string;
  score: number;
  score_pct: number;
  buy_price?: number | null;
  price?: number | null;
  active_buy_ratio?: number | null;
  change_pct?: number | null;
  turnover?: number | null;
  volume_ratio?: number | null;
  money_flow_pass?: boolean | null;
  money_phase_label?: string | null;
  overheat_warning?: string | null;
  accumulation_signal?: string | null;
  new_low_warning?: string | null;
  sector?: string | null;
  sector_change_pct?: number | null;
};

export type CategoryInfo = {
  label: string;
  emoji: string;
  desc: string;
  count: number;
  stocks: CategorizedStock[];
};

export type CategorizedResponse = {
  run_at: string;
  categories: Record<string, CategoryInfo>;
  stats: { total_scanned: number; valid_scored: number };
};

export async function fetchCategorizedRecommend(): Promise<CategorizedResponse> {
  return apiFetch<CategorizedResponse>(CN_ENDPOINTS.recommendCategorized);
}

export type StockSearchResult = {
  symbol: string;
  name: string;
  pinyin: string;
};

export type StockSearchResponse = {
  keyword: string;
  results: StockSearchResult[];
  count: number;
};

export type StockBacktestItem = {
  symbol: string;
  name: string;
  score: number | null;
  entry_date?: string;
  exit_date?: string;
  entry_price?: number;
  exit_price?: number;
  return: number | null;
  win: boolean | null;
  actual_hold_days?: number;
  note?: string;
};

export type StockBacktestKpi = {
  avg_return: number;
  win_rate: number;
  max_return: number;
  min_return: number;
  positive_count: number;
  negative_count: number;
  total: number;
  valid: number;
};

export type StockBacktestResponse = {
  total: number;
  results: StockBacktestItem[];
  kpi: StockBacktestKpi;
  config: any;
  method: string;
};

export async function searchStocksPinyin(keyword: string): Promise<StockSearchResponse> {
  return apiFetch<StockSearchResponse>(
    `${CN_ENDPOINTS.recommend.replace('/recommend', '/stock-search')}?keyword=${encodeURIComponent(keyword)}`
  );
}

export async function postStockBacktest(config: {
  symbols: string[];
  startDate: string;
  endDate: string;
  holdingDays: number;
}): Promise<StockBacktestResponse> {
  return apiFetch<StockBacktestResponse>(
    `${CN_ENDPOINTS.backtest}/stock`,
    { method: "POST", body: JSON.stringify(config) }
  );
}

export type StockNewsItem = {
  title: string;
  url: string;
  time: string;
  source?: string;
};

export async function fetchStockNews(symbol: string): Promise<StockNewsItem[]> {
  const sym = symbol.replace(/^(sh|sz)/, "").toUpperCase();
  return apiFetch<StockNewsItem[]>(`/api/v1/cn/stock/${sym}/news`);
}

export type PaperTradingPosition = {
  symbol: string;
  name: string;
  entry_price: number;
  current_price: number;
  quantity: number;
  pnl_pct: number;
  pnl_amount: number;
  stop_loss: number;
  take_profit: number;
  days_held: number;
  strategy_id: string;
  buy_date: string;
};

export type PaperTradingSignal = {
  symbol: string;
  name: string;
  score: number;
  action: "buy" | "sell";
  price: number;
  target_price: number;
  quantity: number;
  strategy_id: string;
  reason: string;
};

export type PaperTradingStrategy = {
  id: string;
  name: string;
  status: string;
  allocated: number;
  used: number;
  pnl_pct: number;
  positions: PaperTradingPosition[];
  signals: PaperTradingSignal[];
  history: any[];
};

export type PaperTradingAccount = {
  total_assets: number;
  market_value: number;
  cash: number;
  total_pnl_pct: number;
  total_pnl_amount: number;
  daily_pnl_pct: number;
  daily_pnl_amount: number;
  max_drawdown: number;
  trade_count: number;
  win_count: number;
  win_rate: number;
};

export type TradeLogEntry = {
  time: string;
  symbol: string;
  name: string;
  action: "买入" | "卖出" | "止损" | "止盈";
  price: number;
  quantity: number;
  amount: number;
  strategy_id: string;
  pnl_pct?: number;
};

export type PaperTradingData = {
  account: PaperTradingAccount;
  strategies: PaperTradingStrategy[];
  trade_log: TradeLogEntry[];
  updated_at: string;
  next_execution: Record<string, string>;
};

export async function fetchPaperTrading(): Promise<PaperTradingData> {
  return apiFetch<PaperTradingData>("/api/v1/cn/paper-trading");
}

export async function updatePaperTrading(payload: any): Promise<any> {
  return apiFetch<any>("/api/v1/cn/paper-trading/update", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type FeatureFlagsData = {
  features: Record<string, { enabled: boolean; has_access: boolean; label: string }>;
  user_role: string;
};

export async function fetchFeatureFlags(): Promise<FeatureFlagsData> {
  return apiFetch<FeatureFlagsData>("/api/v1/cn/features");
}

export async function updateAllocationConfig(config: {
  total_allocatable?: number;
  ratios?: Record<string, number>;
  reserved?: number;
}): Promise<any> {
  return apiFetch<any>("/api/v1/cn/paper-trading/config", {
    method: "POST",
    body: JSON.stringify({ allocation_config: config }),
  });
}
