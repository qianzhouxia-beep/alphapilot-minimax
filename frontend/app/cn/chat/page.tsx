// AlphaPilot AI 问股 / Agent 对话 — 前端 mock 版 (2026-07-06)
// 提供自然语言交互界面，支持股票搜索、Agent 辩论数据展示
// 后端 AI 对话接口待接入，当前为前端模拟响应
"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import { searchCNStocks, postCNChat, type SearchResult } from "@/lib/cn-api";

// ---------- types ----------
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  stock?: {
    symbol: string;
    name: string;
    score: number;
    price?: number;
    change_pct?: number;
  };
  agentResults?: AgentVote[];
};

type AgentVote = {
  agent: string;
  vote: "赞同" | "反对" | "中性";
  reason: string;
};

// ---------- Agent 元信息（用于右侧说明面板） ----------
const AGENT_LIST = [
  { key: "lhb", name: "龙虎榜 Agent", color: "#A78BFA" },
  { key: "block", name: "大宗交易 Agent", color: "#35e0a3" },
  { key: "limit_up", name: "涨停 Agent", color: "#F5C451" },
  { key: "margin", name: "融资融券 Agent", color: "#C084FC" },
  { key: "research", name: "研报 Agent", color: "#3EE6A8" },
  { key: "news", name: "舆情 Agent", color: "#FF9A5C" },
  { key: "technical", name: "技术 Agent", color: "#C084FC" },
  { key: "sector", name: "板块轮动 Agent", color: "#FF5D5D" },
];

// ---------- preset questions ----------
const PRESET_QUESTIONS = [
  "今天 AI 推荐的 Top 3 股票是哪些？",
  "帮我分析一下大盘走势",
  "今日市场热点板块有哪些？",
  "最近哪个 Agent 判断最准确？",
];

// ---------- component ----------
export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "你好！我是 AlphaPilot AI 问股助手。我可以帮你分析个股、查询市场热点、解读 Agent 辩论结果。你想了解什么？",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showSearch, setShowSearch] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 股票搜索
  const handleSearch = useCallback(async (keyword: string) => {
    if (keyword.length < 1) {
      setShowSearch(false);
      return;
    }
    try {
      const results = await searchCNStocks(keyword);
      setSearchResults(results.slice(0, 5));
      setShowSearch(results.length > 0);
    } catch {
      setSearchResults([]);
      setShowSearch(false);
    }
  }, []);

  // 发送消息（调用真实后端分析引擎）
  const handleSend = async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setShowSearch(false);
    setLoading(true);

    try {
      const resp = await postCNChat(q);
      const reply: Message = {
        id: Date.now().toString() + "_a",
        role: "assistant",
        content: resp.content,
        stock: resp.stock
          ? {
              symbol: resp.stock.symbol,
              name: resp.stock.name,
              score: resp.stock.score,
              price: resp.stock.price,
              change_pct: resp.stock.change_pct,
            }
          : undefined,
        agentResults: resp.agent_results ?? undefined,
      };
      setMessages((prev) => [...prev, reply]);
    } catch (e) {
      const errMsg: Message = {
        id: Date.now().toString() + "_e",
        role: "assistant",
        content: `⚠️ 调用分析服务失败：${e instanceof Error ? e.message : String(e)}。请稍后重试。`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  // 选择搜索建议
  const handleSelectStock = (stock: SearchResult) => {
    setInput(stock.symbol);
    setShowSearch(false);
    handleSend(stock.symbol);
  };

  // 预设问题点击
  const handlePreset = (q: string) => {
    setInput(q);
    handleSend(q);
  };

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen flex flex-col">
      <HeaderBar market="cn" />

      <div className="flex-1 flex flex-col lg:flex-row gap-6 mt-4 min-h-0">
        {/* 左侧 — 聊天区域 */}
        <div className="flex-1 flex flex-col glass card-lift rounded-2xl overflow-hidden min-h-[600px]">
          {/* 聊天头部 */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-border-subtle">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-status-info to-status-success flex items-center justify-center text-[14px] font-bold text-background">
              AI
            </div>
            <div>
              <h2 className="text-[15px] font-semibold text-text-primary">AI 问股助手</h2>
              <p className="text-[11px] text-text-disabled">全市场 5000+ 股票 · 按需 ML 评分</p>
            </div>
          </div>

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                {/* 头像 */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-bold shrink-0 ${
                    msg.role === "user"
                      ? "bg-status-info text-background"
                      : "bg-[rgba(77,163,255,0.15)] text-status-info"
                  }`}
                >
                  {msg.role === "user" ? "U" : "AI"}
                </div>

                {/* 气泡 */}
                <div className={`max-w-[80%] ${msg.role === "user" ? "text-right" : ""}`}>
                  <div
                    className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                      msg.role === "user"
                        ? "bg-status-info text-background"
                        : "bg-surface-panel border border-border-subtle text-text-primary"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>

                    {/* 股票信息卡 */}
                    {msg.stock && (
                      <div className="mt-3 p-3 rounded-xl bg-[rgba(77,163,255,0.08)] border border-[rgba(77,163,255,0.2)]">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[14px] font-bold text-status-info">
                            {msg.stock.symbol}
                          </span>
                          <span
                            className={`text-[20px] font-bold ${
                              msg.stock.score >= 0.65 ? "text-status-success" : "text-status-warning"
                            }`}
                          >
                            {(msg.stock.score * 100).toFixed(0)}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] text-text-secondary">{msg.stock.name}</p>
                      </div>
                    )}

                    {/* Agent 辩论结果 */}
                    {msg.agentResults && msg.agentResults.length > 0 && (
                      <div className="mt-3 space-y-1.5">
                        <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
                          8 Agent 辩论结果
                        </p>
                        {msg.agentResults.map((a, i) => (
                          <div
                            key={i}
                            className="flex items-start gap-2 p-2 rounded-lg bg-[rgba(0,0,0,0.2)]"
                          >
                            <span
                              className={`shrink-0 text-[11px] font-bold px-1.5 py-0.5 rounded ${
                                a.vote === "赞同"
                                  ? "bg-[rgba(62,230,168,0.15)] text-status-success"
                                  : a.vote === "反对"
                                  ? "bg-[rgba(255,93,93,0.15)] text-status-danger"
                                  : "bg-[rgba(159,176,199,0.15)] text-text-secondary"
                              }`}
                            >
                              {a.vote}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-[12px] font-medium text-text-primary">{a.agent}</p>
                              <p className="text-[11px] text-text-secondary truncate">{a.reason}</p>
                            </div>
                          </div>
                        ))}

                        {/* 汇总 */}
                        {(() => {
                          const approve = msg.agentResults.filter((a) => a.vote === "赞同").length;
                          const oppose = msg.agentResults.filter((a) => a.vote === "反对").length;
                          const neutral = msg.agentResults.length - approve - oppose;
                          return (
                            <div className="flex items-center gap-3 text-[11px] text-text-disabled pt-1">
                              <span>✅ {approve} 赞同</span>
                              <span>❌ {oppose} 反对</span>
                              <span>➖ {neutral} 中性</span>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                  <p className="mt-1 text-[10px] text-text-disabled px-1">
                    {msg.role === "user" ? "你" : "AI 助手"}
                  </p>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-[rgba(77,163,255,0.15)] flex items-center justify-center text-[12px] font-bold shrink-0 text-status-info">
                  AI
                </div>
                <div className="rounded-2xl px-4 py-3 bg-surface-card card-lift border border-border-subtle">
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-status-info animate-bounce" />
                    <span className="w-1.5 h-1.5 rounded-full bg-status-info animate-bounce" style={{ animationDelay: "0.2s" }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-status-info animate-bounce" style={{ animationDelay: "0.4s" }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* 输入区域 */}
          <div className="border-t border-border-subtle px-5 py-4">
            <div className="relative flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    handleSearch(e.target.value);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleSend(input)}
                  placeholder="输入股票代码或名称，或直接提问..."
                  className="w-full rounded-xl border border-border-subtle bg-surface-panel px-4 py-3 text-[13px] text-text-primary outline-none placeholder:text-text-disabled focus:border-status-info"
                />

                {/* 搜索建议 */}
                {showSearch && searchResults.length > 0 && (
                  <div className="absolute bottom-full left-0 right-0 mb-1 rounded-xl border border-border-subtle bg-surface-panel overflow-hidden shadow-xl">
                    {searchResults.map((s) => (
                      <button
                        key={s.symbol}
                        onClick={() => handleSelectStock(s)}
                        className="w-full flex items-center justify-between px-4 py-2.5 text-[13px] hover:bg-[rgba(77,163,255,0.08)] text-left"
                      >
                        <span>
                          <span className="font-mono text-status-info">{s.symbol.replace(/\.(SH|SZ)$/, "")}</span>
                          <span className="ml-2 text-text-primary">{s.name}</span>
                        </span>
                        {s.score != null && (
                          <span className="text-[12px] text-text-secondary">{s.sector ?? ""}</span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                onClick={() => handleSend(input)}
                disabled={!input.trim() || loading}
                className="shrink-0 w-11 h-11 rounded-xl bg-gradient-to-r from-status-info to-status-success flex items-center justify-center text-background hover:shadow-lg hover:shadow-status-info/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* 右侧 — 预设问题 & 快捷面板 */}
        <div className="lg:w-72 space-y-4">
          {/* 预设问题 */}
          <div className="glass card-lift rounded-2xl p-5">
            <h3 className="text-[13px] font-semibold text-text-primary mb-3">常见问题</h3>
            <div className="space-y-2">
              {PRESET_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handlePreset(q)}
                  className="w-full text-left rounded-xl border border-border-subtle bg-surface-panel px-3.5 py-2.5 text-[12px] text-text-secondary hover:border-status-info/50 hover:text-text-primary transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* Agent 说明 */}
          <div className="glass card-lift rounded-2xl p-5">
            <h3 className="text-[13px] font-semibold text-text-primary mb-3">8 Agent 辩论系统</h3>
            <div className="space-y-2">
              {AGENT_LIST.map((a) => (
                <div key={a.key} className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: a.color }}
                  />
                  <span className="text-[12px] text-text-secondary">{a.name}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 提示 */}
          <div className="glass card-lift rounded-2xl p-5">
            <p className="text-[11px] text-text-disabled leading-relaxed">
              💡 输入任意 A 股代码（如 603123）即可查看实时分析 + 8 Agent 辩论。
              支持全市场 5000+ 只股票的按需评分与 ML 推理。也支持名称搜索（如"贵州茅台"）。
            </p>
          </div>
        </div>
      </div>

      <footer className="mt-6 text-center text-[11px] text-text-disabled">
        AlphaPilot AI 问股助手 — 仅供教育用途，非投资建议。
      </footer>
    </main>
  );
}
