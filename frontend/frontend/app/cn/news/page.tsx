"use client";

import { useState, useEffect } from "react";
import { HeaderBar } from "@/components/HeaderBar";

const API_BASE = typeof window !== "undefined" && window.location.hostname === "localhost" ? "https://alphapilot.api-tokenmaster.com" : "";

type NewsItem = { title: string; url: string; time: string; source: string };
type NewsData = { source: string; items: NewsItem[]; total: number; generated_at: string };

export default function NewsPage() {
  const [data, setData] = useState<NewsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [readMore, setReadMore] = useState<Set<number>>(new Set());

  const fetchNews = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/cn/news`, { cache: "no-store" });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const d = await res.json();
      // Support both old and new format
      if (d.industries) {
        const all_items: NewsItem[] = [];
        d.industries.forEach((ind: any) => {
          (ind.items || []).forEach((item: any) => {
            all_items.push({ title: item.zh || item.title, url: item.url, time: item.time, source: item.source });
          });
        });
        setData({ source: "新浪财经", items: all_items, total: all_items.length, generated_at: d.generated_at || "" });
      } else {
        setData(d);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchNews(); }, []);
  useEffect(() => { const id = setInterval(fetchNews, 5 * 60 * 1000); return () => clearInterval(id); }, []);

  const toggleSummary = (i: number) => {
    setReadMore(prev => { const n = new Set(prev); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  };

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />
      <div className="mt-6 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] sm:text-[28px] font-semibold text-text-primary">{'投资资讯'}</h1>
          <p className="mt-1 text-[13px] text-text-disabled">
            {'新浪财经 · 实时财经新闻'}
            {data && ` · ${data.generated_at}`}
          </p>
        </div>
        <button onClick={fetchNews} className="flex items-center gap-1.5 rounded-lg bg-status-info/10 px-3 py-2 text-[13px] text-status-info hover:bg-status-info/20">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
          {'刷新'}
        </button>
      </div>

      {loading && !data && <div className="mt-12 flex justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-status-info border-t-transparent" /></div>}
      {error && !data && (
        <section className="glass mt-12 rounded-2xl p-8 text-center">
          <p className="text-[15px] text-status-danger">{'加载资讯失败'}: {error}</p>
          <button onClick={fetchNews} className="mt-4 rounded-lg bg-status-info px-4 py-2 text-[13px] text-[#00315b]">{'重试'}</button>
        </section>
      )}

      {data && (
        <div className="mt-6 space-y-3">
          {data.items.map((item, i) => (
            <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
              className="glass block rounded-2xl p-4 card-lift transition-all duration-200 hover:bg-status-info/[0.04] hover:border-status-info/30"
              onClick={(e) => { if (item.summary && !readMore.has(i)) { e.preventDefault(); toggleSummary(i); } }}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-[15px] font-semibold text-text-primary leading-snug">{item.title}</h3>
                </div>
                {!item.summary && (
                  <svg className="shrink-0 mt-1 text-status-info" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                )}
              </div>
              <div className="mt-3 flex items-center gap-3 text-[11px] text-text-disabled">
                <span className="tag-badge">{item.source}</span>
                <span>{item.time}</span>
              </div>
            </a>
          ))}
        </div>
      )}

      <footer className="mt-10 text-center text-[11px] text-text-disabled">{'新浪财经 · 仅供教育用途，非投资建议'}</footer>
    </main>
  );
}