// AlphaPilot A 鑲?Dashboard 鈥?V15 鐪熷疄绛圭爜妯″瀷 (2026-07-09)
// Zeabur HTTPS -> cn_proxy.py -> 鑵捐浜?150.158.100.236
// 2026-07-13: 60绉掕疆璇?/recommend/live 瀹炴椂璧勯噾娴侊紙鐩樹腑闃舵鏍囩瀹炴椂鍒锋柊锛?"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchCNScreener, fetchWatchlist, addToWatchlist, removeFromWatchlist,
  fetchCategorizedRecommend, fetchLiveRecommend,
  type ScreenerItem, type ScreenerResponse, type WatchlistItem,
  type CategorizedResponse,
} from "@/lib/cn-api";
import PhaseGroupCard, { PHASE_GROUPS } from "@/components/PhaseGroupCard";

const scoreColor = (s: number) =>
  s >= 0.50 ? "text-[#3EE6A8]" : s >= 0.40 ? "text-[#4DA3FF]" : s >= 0.30 ? "text-[#F5C451]" : "text-[#9FB0C7]";
const displayScore = (s: number) => Math.min(99, Math.max(75, Math.round(s * 45 + 75)));
const scoreLabel = (s: number) =>
  s >= 0.50 ? "A+" : s >= 0.35 ? "A" : s >= 0.25 ? "B+" : "B";

export default function CNDashboard() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [watchlistSymbols, setWatchlistSymbols] = useState<Set<string>>(new Set());
  const [wlData, setWlData] = useState<WatchlistItem[]>([]);
  const [wlLoading, setWlLoading] = useState<Record<string, boolean>>({});
  const [wlMsg, setWlMsg] = useState<{ type: string; text: string } | null>(null);
  const [catData, setCatData] = useState<CategorizedResponse | null>(null);
  const [catLoading, setCatLoading] = useState(true);
  const [priceDialog, setPriceDialog] = useState<{ item: any; price: string } | null>(null);
  const [priceDialogLoading, setPriceDialogLoading] = useState(false);
  // 瀹炴椂鐘舵€佹爣璁?  const [liveTs, setLiveTs] = useState<number>(0);
  const [livePolling, setLivePolling] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [d, wl, cat] = await Promise.all([fetchCNScreener(), fetchWatchlist(), fetchCategorizedRecommend()]);
      setData(d);
      setWlData(wl.watchlist || []);
      setWatchlistSymbols(new Set((wl.watchlist || []).map((w: WatchlistItem) => w.symbol)));
      setCatData(cat);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      await loadData();
      if (!cancelled) { setLoading(false); setCatLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // 30 min auto refresh (鍏ㄩ噺璇勫垎+鍒嗙被)
  useEffect(() => {
    const id = setInterval(loadData, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // 杞璁℃暟鍣細姣?娆★紙5鍒嗛挓锛夎Е鍙戜竴娆″姩鎬侀噸鎺?  const rerankCounterRef = useRef(0);

  // 60绉掑疄鏃惰祫閲戞祦鍒锋柊 + 姣?鍒嗛挓鍔ㄦ€侀噸鎺?  useEffect(() => {
    const pollLive = async () => {
      if (document.hidden) return; // 鏍囩椤甸殣钘忔椂涓嶈疆璇?      // 闈炰氦鏄撴椂闂翠笉杞锛?:25-15:05 涓轰氦鏄撴椂娈碉紝浠呭伐浣滄棩锛?      const _now = new Date();
      const _h = _now.getHours(), _m = _now.getMinutes(), _d = _now.getDay();
      const _isWeekend = _d === 0 || _d === 6;
      const _isBeforeOpen = _h < 9 || (_h === 9 && _m < 25);
      const _isAfterClose = _h > 15 || (_h === 15 && _m > 5);
      const _isLunchBreak = _h === 11 && _m > 30;
      if (_isWeekend || _isBeforeOpen || _isAfterClose || _isLunchBreak) return;
      setLivePolling(true);
      rerankCounterRef.current += 1;
      // 绗?娆★紙椤甸潰鍔犺浇5绉掑悗锛夊拰姝ゅ悗姣?娆★紙姣?鍒嗛挓锛夊仛鍔ㄦ€侀噸鎺?      const isRerank = rerankCounterRef.current === 1 || rerankCounterRef.current % 5 === 0;

      try {
        // 閲嶆帓鏃讹細rerank=true 鑾峰彇 Top 100 鍔ㄦ€侀噸鎺?        // 鍏朵粬鏃跺€欙細鏅€?0绉掑瓧娈靛悎骞?        const topN = isRerank ? 100 : 50;
        const live = await fetchLiveRecommend(topN, isRerank);
        setLiveTs(live.ts || Date.now() / 1000);

        // 閲嶆帓鏃讹細鐩存帴鏇挎崲鏁翠釜鎺ㄨ崘鍒楄〃
        if (isRerank && live.rerank && live.data && live.data.length > 0) {
          // 鍙彇閲嶆帓鍚庣殑鍓?0鍙紙鎻愬崌鎬ц兘锛?          const reranked = live.data.slice(0, 10).map((it: any) => ({
            ...it,
            _reranked: true,
          }));
          setData((prev) => {
            if (!prev) return prev;
            return { ...prev, recommendations: reranked };
          });
          console.log(`[rerank] ${new Date().toLocaleTimeString()} 鍔ㄦ€侀噸鎺掑畬鎴恅);
        } else if (live && live.data && live.data.length > 0) {
          // 鏅€?0绉掞細瀛楁绾у悎骞讹紙涓嶆敼鍙樻帓鍚嶏級
          setData((prev) => {
            if (!prev) return prev;
            const liveMap = new Map(live.data.map((it: any) => [it.symbol, it]));
            const updated = prev.recommendations.map((it: any) => {
              const liveItem = liveMap.get(it.symbol);
              if (liveItem) {
                const isLiveReal = liveItem._data_source === "live";
                const currentAbr = it.active_buy_ratio;
                const liveAbr = liveItem.active_buy_ratio;
                const finalAbr = isLiveReal
                  ? liveAbr
                  : (currentAbr !== undefined && currentAbr !== null ? currentAbr : liveAbr);
                return {
                  ...it,
                  active_buy_ratio: finalAbr,
                  money_phase_label: isLiveReal
                    ? (liveItem.money_phase_label ?? it.money_phase_label)
                    : (it.money_phase_label ?? liveItem.money_phase_label),
                  change_pct: isLiveReal
                    ? (liveItem.change_pct ?? it.change_pct)
                    : (it.change_pct ?? liveItem.change_pct),
                  turnover: isLiveReal
                    ? (liveItem.turnover ?? it.turnover)
                    : (it.turnover ?? liveItem.turnover),
                  price: isLiveReal
                    ? (liveItem.price ?? it.price)
                    : (it.price ?? liveItem.price),
                };
              }
              return it;
            });
            return { ...prev, recommendations: updated };
          });
        }
      } catch (e) {
        console.warn("[live poll]", e);
      } finally {
        setLivePolling(false);
      }
    };
    // 棣栨寤惰繜 5 绉掞紝绛夊垵濮?loadData 瀹屾垚
    const initial = setTimeout(pollLive, 5000);
    const id = setInterval(pollLive, 60 * 1000);
    return () => { clearTimeout(initial); clearInterval(id); };
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const handleToggleWatchlist = async (item: ScreenerItem) => {
    const sym = item.symbol.replace(/^(sh|sz)/, "");
    if (watchlistSymbols.has(sym)) {
      try {
        await removeFromWatchlist(sym);
        setWatchlistSymbols(prev => { const n = new Set(prev); n.delete(sym); return n; });
        setWlMsg({ type: "success", text: `宸插彇娑堟敹钘?${item.name}` });
      } catch (e: any) {
        setWlMsg({ type: "error", text: e.message || "鎿嶄綔澶辫触" });
      }
      setTimeout(() => setWlMsg(null), 3000);
      try { const wl = await fetchWatchlist(); setWlData(wl.watchlist || []); } catch {}
    } else {
      const defaultPrice = item.buy_price || 0;
      setPriceDialog({ item, price: (defaultPrice > 0 ? defaultPrice : "").toString() });
    }
  };

  const confirmAddWatchlist = async () => {
    if (!priceDialog) return;
    const item = priceDialog.item;
    const sym = item.symbol.replace(/^(sh|sz)/, "");
    const price = parseFloat(priceDialog.price);
    if (isNaN(price) || price <= 0) {
      setWlMsg({ type: "error", text: "璇疯緭鍏ユ湁鏁堢殑涔板叆浠锋牸" });
      setTimeout(() => setWlMsg(null), 3000);
      return;
    }
    setPriceDialogLoading(true);
    try {
      await addToWatchlist(sym, item.name, price, item.score || 0);
      setWatchlistSymbols(prev => new Set(prev).add(sym));
      setWlMsg({ type: "success", text: `宸叉坊鍔犳敹钘?${item.name} @ 楼${price.toFixed(2)}` });
      setPriceDialog(null);
    } catch (e: any) {
      setWlMsg({ type: "error", text: e.message || "娣诲姞澶辫触" });
    }
    setPriceDialogLoading(false);
    setTimeout(() => setWlMsg(null), 3000);
    try { const wl = await fetchWatchlist(); setWlData(wl.watchlist || []); } catch {}
  };

  const items = data?.recommendations ?? [];
  const buildSectorChanges = (stockList: any[]) => {
    const groups: Record<string, number[]> = {};
    stockList.forEach((it: any) => {
      const sec = it.sector;
      const chg = it.change_pct;
      if (sec && chg != null) {
        if (!groups[sec]) groups[sec] = [];
        groups[sec].push(chg);
      }
    });
    const result: Record<string, number> = {};
    Object.entries(groups).forEach(([sec, chgs]) => {
      if (chgs.length < 2) return; // 鍙湁1鍙偂绁ㄦ椂涓嶆樉绀烘澘鍧楁定璺屽箙锛岄伩鍏嶇瓑浜庝釜鑲¤嚜韬?      chgs.sort((a: number, b: number) => a - b);
      result[sec] = chgs[Math.floor(chgs.length / 2)];
    });
    return result;
  };
  const sectorChanges = buildSectorChanges(items);
  if (catData) {
    const catStocks = Object.values(catData.categories).flatMap((cat: any) => cat.stocks || []);
    const catChanges = buildSectorChanges(catStocks);
    Object.entries(catChanges).forEach(([k, v]) => { sectorChanges[k] = v; });
  }
  const markupStocks = catData?.categories?.markup?.stocks ?? [];
  const isMarkupTop = markupStocks.length > 0;
  const top = isMarkupTop
    ? markupStocks.reduce((best, s) => s.score_pct > best.score_pct ? s : best, markupStocks[0])
    : (items.find(it => it.money_flow_pass === true) || items[0]);
  const avgScore = items.length ? (items.reduce((s, i) => s + i.score, 0) / items.length) : 0;
  const returnedCount = data?.stats?.returned ?? items.length;

  // 瀹炴椂鐘舵€佹樉绀?  const liveAgo = liveTs > 0 ? Math.max(0, Math.floor(Date.now() / 1000 - liveTs)) : null;
  const liveStatusText = liveAgo === null
    ? "绛夊緟棣栨瀹炴椂鍒锋柊"
    : liveAgo < 5 ? "鍒氬垰"
    : liveAgo < 60 ? `${liveAgo}绉掑墠`
    : `${Math.floor(liveAgo / 60)}鍒嗛挓鍓峘;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {wlMsg && (
        <div className={`fixed top-20 right-4 z-50 rounded-xl p-4 shadow-2xl ${
          wlMsg.type === "success" ? "bg-[rgba(62,230,168,0.15)] border border-[#3EE6A8]" : "bg-[rgba(255,93,93,0.15)] border border-[#FF5D5D]"
        }`}>
          <p className="text-[13px] text-[#EAF2FF]">{wlMsg.text}</p>
        </div>
      )}

      {error && (
        <div className="glass mb-6 rounded-2xl border border-[#FF5D5D] p-4">
          <div className="flex items-start gap-3">
            <svg className="w-6 h-6 shrink-0 text-[#FF5D5D]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="flex-1">
              <p className="text-sm text-[#FF5D5D] font-semibold">鍚庣鏃犳硶杩炴帴</p>
              <p className="mt-1 text-[12px] text-[#9FB0C7]">{error}</p>
              <button onClick={handleRefresh} className="mt-3 rounded-lg bg-[#FF5D5D] px-4 py-2 text-[12px] font-semibold text-white hover:bg-[#ff7a7a]">
                閲嶈瘯
              </button>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
        <div className="w-full h-px bg-gradient-to-r from-transparent via-[#4DA3FF]/30 to-transparent mb-6"></div>
        <section className="mb-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
          <KPI label="浠婃棩鏈€浣? value={top ? top.name : "鈥?} sub={top ? `${top.symbol.replace(/^(sh|sz)/,"")} 路 ${displayScore(top.score)}淇″績${isMarkupTop ? " 路 鎷夊崌纭" : top.money_phase_label ? " 路 " + top.money_phase_label : ""}` : ""} accent="#3EE6A8" />
          <KPI label="瀹炴椂璧勯噾" value={livePolling ? "鎷夊彇涓? : (liveAgo != null ? "鉁? : "鈥?)} sub={`璧勯噾娴?${liveStatusText} 路 60绉掑埛鏂癭} accent="#F5C451" />
          <KPI label="浠婃棩鎺ㄨ崘" value={`${returnedCount}`} sub={`${items.length} 鍙€氳繃闂ㄦ帶 路 鎺掑悕鍓?{Math.round(items.length / (data?.stats?.total_scanned || 1) * 100)}%`} accent="#3EE6A8" />
          <KPI label="骞冲潎淇″績" value={`${displayScore(avgScore)}`} sub={`淇″績鍒?{(avgScore * 100).toFixed(0)}% 鍘熷`} accent="#4DA3FF" />
          <KPI label="鍏ㄩ噺鎵弿" value={`${data.stats.valid_scored}`} sub={`${data.stats.total_scanned} 鍙?路 ${(data.stats.elapsed_seconds / 60).toFixed(0)}m 路 鑷垜瀛︿範`} accent="#F5C451" />
        </section>
        </>
      )}

      <section className="glass rounded-2xl p-4 sm:p-6 mb-6">
        <div className="mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-1 h-6 rounded-full bg-[#4DA3FF]"></div>
              <h2 className="text-[18px] font-semibold text-[#EAF2FF]">A 鑲?Top 10 鏈轰細</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(77,163,255,0.12)] text-[#4DA3FF] border border-[rgba(77,163,255,0.25)]">V18</span>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#3EE6A8] animate-pulse"></span>
                  5鍒嗛挓鍔ㄦ€侀噸鎺?                </span>
              )}
              {liveTs > 0 && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#F5C451] animate-pulse"></span>
                  瀹炴椂 {liveStatusText}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[12px] text-[#6E7C93]">
              V18 Fusion 鍐崇瓥绯荤粺 路 30缁磋瀺鍚堢壒寰?路 5妯″瀷闆嗘垚 路 鍑屾櫒 5:00 閫夎偂 路 鍚殧澶滅編鑲″奖鍝嶅洜瀛?路 閲忔瘮鎹㈡墜闂ㄦ帶 路 鑷垜鎻愬崌瀛︿範 路 鐩樹腑60绉掑疄鏃惰祫閲戝埛鏂?路 姣?鍒嗛挓鍔ㄦ€侀噸鎺?路 Top 10 瀹屾暣姒滃崟
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/cn/watchlist" className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-1.5 text-[12px] text-[#F5C451] hover:border-[#F5C451] transition-colors flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              鏀惰棌杩借釜
            </Link>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-1.5 text-[12px] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF] disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <svg className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              {refreshing ? "鍒锋柊涓?.." : "鍒锋柊"}
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]"></div>
            <p className="mt-4 text-[14px] text-[#9FB0C7]">鍔犺浇涓?..</p>
          </div>
        )}

        {data && (
          <div className="overflow-x-auto">
            <table className="w-full table-fixed">
              <colgroup>
                <col className="w-[4%]" />
                <col className="w-[9%]" />
                <col className="w-[14%]" />
                <col className="w-[12%]" />
                <col className="w-[10%]" />
                <col className="w-[12%]" />
                <col className="w-[9%]" />
                <col className="w-[10%]" />
                <col className="w-[10%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-[#1D2A42] text-[11px] uppercase tracking-wider text-[#6E7C93]">
                  <th className="px-3 py-3 font-medium text-left">#</th>
                  <th className="px-3 py-3 font-medium text-left">浠ｇ爜</th>
                  <th className="px-3 py-3 font-medium text-left hidden sm:table-cell">鍚嶇О</th>
                  <th className="px-3 py-3 font-medium text-left hidden lg:table-cell">鏉垮潡</th>
                  <th className="px-3 py-3 font-medium text-right">璇勫垎</th>
                  <th className="px-3 py-3 font-medium text-left hidden xl:table-cell">璧勯噾</th>
                  <th className="px-3 py-3 font-medium text-left hidden 2xl:table-cell">鍩烘湰</th>
                  <th className="px-3 py-3 font-medium text-right">鐜颁环</th>
                  <th className="px-3 py-3 font-medium text-right hidden xl:table-cell">鐩爣浠?/th>
                  <th className="px-3 py-3 font-medium text-left">鎿嶄綔</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => {
                  const sym = item.symbol.replace(/^(sh|sz)/, "");
                  const isFav = watchlistSymbols.has(sym);
                  const isWlLoading = wlLoading[sym] ?? false;
                  return (
                  <tr key={item.symbol} className="border-b border-[#1D2A42]/50 hover:bg-[rgba(77,163,255,0.04)]">
                    <td className="px-3 py-3 text-left text-[12px] text-[#6E7C93] font-display-numeric">
                      {String(i + 1).padStart(2, "0")}
                    </td>
                    <td className="px-3 py-3 text-left">
                      <span className="font-mono text-[14px] font-semibold text-[#4DA3FF]">{sym}</span>
                    </td>
                    <td className="px-3 py-3 text-left text-[13px] text-[#EAF2FF] hidden sm:table-cell">
                      <Link href={`/cn/stock?symbol=${item.symbol}`} className="hover:text-[#4DA3FF] transition-colors">{item.name}</Link>
                    </td>
                    <td className="px-3 py-3 text-left hidden lg:table-cell">
                      {item.sector ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(77,163,255,0.12)] px-2 py-0.5 text-[11px] font-medium text-[#4DA3FF] border border-[rgba(77,163,255,0.25)] max-w-[180px] whitespace-nowrap">
                          <span className="truncate">{item.sector}</span>
                          {item.sector_change_pct != null && (
                            <span className={`shrink-0 ${
                              item.sector_change_pct >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"
                            }`}>
                              {item.sector_change_pct > 0 ? "+" : ""}{item.sector_change_pct.toFixed(1)}%
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-[12px] text-[#6E7C93]">鈥?/span>
                      )}
                    </td>
                    <td className={`px-3 py-3 text-right ${scoreColor(item.score)}`}>
                      <div className="flex flex-col items-end">
                        <span className="font-display-numeric text-[22px] font-bold leading-none">
                          {displayScore(item.score)}<span className="text-[13px]">淇″績</span>
                        </span>
                        {item.score_label && (
                          <span className="text-[10px] text-[#6E7C93] mt-0.5">{item.score_label}</span>
                        )}
                        <span className={`text-[9px] font-medium ${scoreColor(item.score)}`}>
                          {scoreLabel(item.score)}
                          {item.score >= 0.45 && ' '}<svg className="inline-block w-3 h-3 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                          {item.score >= 0.55 && '馃敟'}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-left hidden xl:table-cell">
                      {item.active_buy_ratio != null ? (
                        <div className="flex flex-col gap-1">
                          <span className={`text-[12px] font-display-numeric ${item.active_buy_ratio >= 0.5 ? "text-[#3EE6A8]" : "text-[#FF5D5D]"}`}>
                            {(item.active_buy_ratio * 100).toFixed(0)}% 涓诲姩涔板叆
                          </span>
                          {item.money_phase_label && (
                            <span className="text-[11px] text-[#F5C451]">{item.money_phase_label}</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[12px] text-[#6E7C93]">鈥?/span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-left hidden 2xl:table-cell">
                      {item.eps != null ? (
                        <div className="flex flex-col gap-1">
                          <span className="text-[12px] font-display-numeric text-[#EAF2FF]">
                            EPS {item.eps.toFixed(2)}
                          </span>
                          {item.fundamental_pass === true && (
                            <span className="inline-flex w-fit items-center rounded-full bg-[rgba(62,230,168,0.15)] px-1.5 py-0.5 text-[10px] font-medium text-[#3EE6A8]">鐩堝埄</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[12px] text-[#6E7C93]">鈥?/span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right text-[14px] text-[#EAF2FF] font-display-numeric">
                      {(() => {
                        const curPrice = item.buy_price > 0 && item.change_pct != null
                          ? (item.buy_price * (1 + item.change_pct / 100)).toFixed(2)
                          : null;
                        return curPrice ? `${curPrice}` : (item.buy_price > 0 ? item.buy_price.toFixed(2) : "鈥?);
                      })()}
                      {item.buy_price > 0 && (
                        <span className="block text-[9px] text-[#6E7C93] font-normal">鏄ㄦ敹 楼{item.buy_price.toFixed(2)}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right text-[13px] text-[#3EE6A8] font-display-numeric hidden xl:table-cell">
                      {item.target_price > 0 ? item.target_price.toFixed(2) : "鈥?}
                    </td>
                    <td className="px-3 py-3 text-left">
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-nowrap">
                        <button
                          onClick={() => handleToggleWatchlist(item)}
                          disabled={isWlLoading}
                          className={`rounded-lg px-1.5 sm:px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-50 whitespace-nowrap ${
                            isFav
                              ? "bg-[rgba(245,196,81,0.15)] text-[#F5C451] hover:bg-[rgba(245,196,81,0.25)]"
                              : "border border-[#1D2A42] bg-[#0C1728] text-[#6E7C93] hover:border-[#F5C451] hover:text-[#F5C451]"
                          }`}>
                          {isWlLoading ? "..." : isFav ? "鈽呭凡鏀惰棌" : "鈽嗘敹钘?}
                        </button>
                        <Link href={`/cn/stock?symbol=${item.symbol}`} className="text-[12px] text-[#4DA3FF] hover:underline shrink-0">
                          璇︽儏
                        </Link>
                      </div>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {catData && (
        <section className="mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1 h-6 rounded-full bg-[#F5C451]"></div>
                <h2 className="text-[18px] font-semibold text-[#EAF2FF]">璧勯噾闃舵鍒嗙被</h2>
              </div>
              <p className="mt-0.5 text-[12px] text-[#6E7C93]">
                4 澶ф澘鍧?路 鍑屾櫒 5:00 閫夎偂 路 鍚殧澶滅編鑲″奖鍝?              </p>
            </div>
          </div>
          {catLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-3 border-[#1D2A42] border-t-[#4DA3FF]"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {PHASE_GROUPS.map(group => (
                <PhaseGroupCard key={group.key} group={group}
                  categories={catData.categories || {}}
                  watchlistSymbols={watchlistSymbols} wlLoading={wlLoading}
                  onToggleWatchlist={handleToggleWatchlist} sectorChanges={sectorChanges} />
              ))}
            </div>
          )}
        </section>
      )}

      {wlData.length > 0 && (
        <section className="glass rounded-2xl p-4 sm:p-6 mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2"><svg className="w-5 h-5 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><h2 className="text-[20px] font-semibold text-[#EAF2FF]">鏀惰棌杩借釜</h2></div>
              <p className="mt-0.5 text-[12px] text-[#6E7C93]">
                璁板綍鍏ュ満浠?路 鑷姩杩借釜 T+1/T+2/T+3 娑ㄨ穼
              </p>
            </div>
            <Link href="/cn/watchlist" className="text-[12px] text-[#4DA3FF] hover:underline">
              鏌ョ湅鍏ㄩ儴 鈫?            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[#1D2A42] text-[11px] uppercase tracking-wider text-[#6E7C93]">
                  <th className="px-3 py-2 font-medium">鑲＄エ</th>
                  <th className="px-3 py-2 text-right font-medium">鍏ュ満浠?/th>
                  <th className="px-3 py-2 text-right font-medium">T+1</th>
                  <th className="px-3 py-2 text-right font-medium">T+2</th>
                  <th className="px-3 py-2 text-right font-medium hidden sm:table-cell">T+3</th>
                  <th className="px-3 py-2 font-medium hidden sm:table-cell">鐘舵€?/th>
                </tr>
              </thead>
              <tbody>
                {wlData.slice(0, 5).map((w) => (
                  <tr key={w.id} className="border-b border-[#1D2A42]/50 text-[13px]">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5 flex-nowrap min-w-0">
                        <span className="font-semibold text-[#EAF2FF] truncate">{w.name}</span>
                        <span className="text-[#6E7C93] text-[11px] shrink-0">{w.symbol}</span>
                        {w.sector && (
                          <span className="hidden sm:inline-flex items-center gap-1 text-[9px] px-1 py-0.5 rounded-full bg-[rgba(77,163,255,0.1)] text-[#4DA3FF] border border-[rgba(77,163,255,0.2)] leading-none shrink-0">
                            <span className="truncate max-w-[50px]">{w.sector}</span>
                            {(() => {
                              const sc = (w as any).sector_change_pct ?? sectorChanges[w.sector];
                              return sc != null ? (
                                <span className={`shrink-0 ${
                                  sc >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"
                                }`}>
                                  {sc > 0 ? "+" : ""}{sc.toFixed(1)}%
                                </span>
                              ) : null;
                            })()}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[#F5C451]">{w.entry_price.toFixed(2)}</td>
                    <td className={`px-3 py-2 text-right font-mono ${w.day1_change != null ? (w.day1_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-[#6E7C93]"}`}>
                      {w.day1_change != null ? `${w.day1_change > 0 ? "+" : ""}${w.day1_change}%` : "鈥?}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${w.day2_change != null ? (w.day2_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-[#6E7C93]"}`}>
                      {w.day2_change != null ? `${w.day2_change > 0 ? "+" : ""}${w.day2_change}%` : "鈥?}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono hidden sm:table-cell ${w.day3_change != null ? (w.day3_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-[#6E7C93]"}`}>
                      {w.day3_change != null ? `${w.day3_change > 0 ? "+" : ""}${w.day3_change}%` : "鈥?}
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${w.status === "active" ? "bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]" : "bg-[rgba(159,176,199,0.15)] text-[#9FB0C7]"}`}>
                        {w.status === "active" ? "杩借釜涓? : "鍘嗗彶璁板綍"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="glass rounded-2xl p-4 sm:p-6 mb-6">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-1 h-12 rounded-full bg-[#8B5CF6] shrink-0 mt-1"></div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-5 h-5 text-[#A78BFA]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              <h2 className="text-[17px] font-semibold text-[#EAF2FF]">灏剧洏鐙欏嚮</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(139,92,246,0.12)] text-[#A78BFA] border border-[rgba(139,92,246,0.3)]">14:00</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]">涓€澶滄寔鑲?/span>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(139,92,246,0.15)] text-[#A78BFA] border border-[rgba(139,92,246,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#A78BFA] animate-pulse"></span>
                  鍔ㄦ€侀噸鎺掍腑
                </span>
              )}
            </div>
            <p className="text-[11px] text-[#6E7C93]">
              V19 Fusion 缁煎悎璇勫垎 路 鍔ㄦ€侀噸鎺?Top 3 路 璧勯噾+妯″瀷鍙岄噸绛涢€?路 14:00 鑷姩杈撳嚭
            </p>
          </div>
        </div>

        {items.length > 0 && items[0]?._reranked ? (
          <div className="space-y-2">
            {items.filter((s: any) => {
              const chg = s.change_pct || 0;
              return chg < 9.4; // 杩囨护娑ㄥ仠
            }).slice(0, 3).map((s: any, i: number) => {
              const sym = s.symbol.replace(/^(sh|sz)/, "");
              const chg = s.change_pct || 0;
              const chgColor = chg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]";
              const abr = s.active_buy_ratio || 0.5;
              const net = s.main_net || 0;
              // 璁＄畻瀹炴椂浠锋牸锛堜粠鏄ㄦ敹鍜屾定璺屽箙绠楋紝纭繚涓€鑷达級
              const livePrice = s.buy_price > 0 && s.change_pct != null
                ? (s.buy_price * (1 + s.change_pct / 100)).toFixed(2)
                : (s.price || s.buy_price || 0).toFixed(2);

              // 鍒嗘瀽閫昏緫锛氫负浠€涔堟帹鑽愯繖鍙?              const isUp = chg >= 0;
              const isStrongInflow = abr >= 0.55 && net > 0;
              const isBearTrap = abr >= 0.55 && !isUp && net > 0;
              const isAccumulation = abr >= 0.52 && chg < 2 && chg >= 0;
              const isMarkup = abr >= 0.52 && chg >= 2 && chg < 9.4;

              let advice = "";
              let adviceColor = "";
              if (isBearTrap) {
                advice = "馃 璇辩┖闄烽槺 路 涓嬭穼涓富鍔涙殫涓惛绛癸紝鏄庢棩鏈熷緟鍙嶅脊";
                adviceColor = "text-[#8B5CF6]";
              } else if (isMarkup) {
                advice = "馃殌 涓诲姏鎷夊崌涓?路 璧勯噾+妯″瀷鍙岄噸纭锛屽彲杞讳粨璺熻繘";
                adviceColor = "text-[#EF4444]";
              } else if (isStrongInflow && isUp) {
                advice = "馃挵 璧勯噾寮哄娍 路 鏀鹃噺涓婃定涓诲姏鎸佺画娴佸叆锛岃秼鍔垮悜濂?;
                adviceColor = "text-[#3EE6A8]";
              } else if (isAccumulation) {
                advice = "馃摜 鍚哥闃舵 路 涓诲姏榛橀粯涔板叆浣嗚偂浠锋湭娑紝鑰愬績鎸佹湁";
                adviceColor = "text-[#3B82F6]";
              } else if (net > 0 && abr >= 0.52) {
                advice = "馃搳 璧勯噾娴佸叆涓?路 铏芥湁娉㈠姩浣嗕富鍔涘湪浣庝綅鍚哥";
                adviceColor = "text-[#F5C451]";
              } else {
                advice = "馃搶 缁煎悎璇勫垎闈犲墠 路 寤鸿缁撳悎鏄庢棩鐩橀潰鍒ゆ柇";
                adviceColor = "text-[#9FB0C7]";
              }

              const risk = chg > 7 ? "鈿狅笍 娑ㄥ箙宸查珮" : chg < -7 ? "鈿狅笍 璺屽箙杈冨ぇ" : "鉁?閫備腑";
              const riskColor = chg > 7 ? "text-[#FF5D5D]" : chg < -7 ? "text-[#FF5D5D]" : "text-[#3EE6A8]";

              return (
                <div key={s.symbol} className="sniper-card">
                  <div className="grid grid-cols-[20px_1fr_80px_80px] sm:grid-cols-[20px_1fr_110px_90px_70px] items-center gap-1">
                    <span className="text-[13px] font-bold text-[#A78BFA]">{i + 1}</span>
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Link href={`/cn/stock?symbol=${s.symbol}`} className="text-[13px] font-medium text-[#EAF2FF] hover:text-[#A78BFA] truncate">{s.name}</Link>
                      <span className="text-[10px] text-[#6E7C93] shrink-0">{sym}</span>
                      {s.sector && (
                        <span className="hidden sm:inline text-[10px] px-1.5 py-0.5 rounded-full bg-[rgba(139,92,246,0.1)] text-[#A78BFA] border border-[rgba(139,92,246,0.2)] truncate max-w-[80px]">{s.sector}</span>
                      )}
                    </div>
                    <span className="text-[13px] font-display-numeric text-[#EAF2FF] text-right">{livePrice}</span>
                    <span className={`text-[13px] font-display-numeric font-medium text-right ${chgColor}`}>{chg > 0 ? "+" : ""}{chg.toFixed(1)}%</span>
                    <span className={`hidden sm:block text-[11px] text-right font-medium ${riskColor}`}>{risk}</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
                    <span className={`${adviceColor}`}>{advice}</span>
                    <span className="text-[#4A5568]">路</span>
                    <span className="text-[#9FB0C7]">ABR {(abr * 100).toFixed(0)}%</span>
                    <span className="text-[#4A5568]">路</span>
                    <span className={`font-display-numeric ${net >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"}`}>
                      涓诲姏{net >= 0 ? "+" : ""}{(net / 10000).toFixed(0)}涓?                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg bg-[#121c2a] px-3 py-2 border border-[#1D2A42]">
            <svg className="w-4 h-4 text-[#6E7C93]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <p className="text-[12px] text-[#6E7C93]">椤甸潰鍔犺浇鍚?5 绉掕嚜鍔ㄧ敓鎴?路 杩囨护娑ㄥ仠鑲?路 璧勯噾+妯″瀷缁煎悎璇勫垎 Top 3</p>
          </div>
        )}
      </section>

      <section className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1 h-6 rounded-full bg-[#3EE6A8]"></div>
          <h2 className="text-[18px] font-semibold text-[#EAF2FF]">鑷垜杩涘寲瀛︿範</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.25)]">AI 椹卞姩</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#4DA3FF]">
            <svg className="w-6 h-6 mb-1 text-[#4DA3FF]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            <h3 className="text-[14px] font-semibold text-[#EAF2FF] mb-1">鑷姩鍘嗗彶鍥炴挙</h3>
            <p className="text-[11px] text-[#6E7C93] leading-relaxed">
              姣忔棩 Top 5 鎺ㄨ崘鑷姩璁板綍锛孴+1/T+3 娑ㄨ穼骞呰嚜鍔ㄨ拷韪紝鐢熸垚瀹屾暣鍥炴祴鏁版嵁搴?            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#3EE6A8]">
            <div className="text-[24px] mb-1">馃搳</div>
            <h3 className="text-[14px] font-semibold text-[#EAF2FF] mb-1">鑳滅巼鑷姩缁熻</h3>
            <p className="text-[11px] text-[#6E7C93] leading-relaxed">
              鏀惰棌澶硅嚜鍔ㄨ绠楄儨鐜?骞冲潎鏀剁泭锛屾暟鎹┍鍔ㄨ€岄潪鎰熻椹卞姩
            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#F5C451]">
            <svg className="w-6 h-6 mb-1 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <h3 className="text-[14px] font-semibold text-[#EAF2FF] mb-1">闂ㄦ帶鍙傛暟浼樺寲</h3>
            <p className="text-[11px] text-[#6E7C93] leading-relaxed">
              鍩轰簬鍘嗗彶鏁版嵁鑷姩璋冩暣棣栨澘娲楃洏/閲忔瘮鎹㈡墜闂ㄦ帶鍙傛暟锛屾寔缁彁鍗囧噯纭巼
            </p>
          </div>
        </div>
      </section>

      <footer className="mt-10 text-center text-[11px] text-[#6E7C93]">
        AlphaPilot 鎻愪緵 AI 杈呭姪鍒嗘瀽锛屼粎渚涙暀鑲茬敤閫旓紝闈炴姇璧勫缓璁€傝繃寰€琛ㄧ幇涓嶄繚璇佹湭鏉ユ敹鐩娿€?        <br />
        A 鑲″唴瀹逛粎渚涘湪缇庡崕浜烘暀鑲茬敤閫旓紝闈炰腑鍥藉鍐呮姇椤炬湇鍔°€?      </footer>

      {priceDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => !priceDialogLoading && setPriceDialog(null)}>
          <div className="w-[90vw] max-w-[380px] rounded-2xl border border-[#1D2A42] bg-[#0C1728] p-6 shadow-2xl mx-4"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-1"><svg className="w-5 h-5 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><h3 className="text-[18px] font-semibold text-[#EAF2FF]">娣诲姞鏀惰棌</h3></div>
            <p className="text-[13px] text-[#9FB0C7] mb-4">
              {priceDialog.item.name} 路 {priceDialog.item.symbol?.replace(/^(sh|sz)/, "")}
            </p>
            <label className="block mb-1 text-[12px] text-[#6E7C93]">涔板叆浠锋牸锛埪ワ級</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={priceDialog.price}
              onChange={e => setPriceDialog(prev => prev ? { ...prev, price: e.target.value } : null)}
              className="w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2.5 text-[16px] text-[#EAF2FF] font-mono outline-none focus:border-[#4DA3FF] transition-colors"
              placeholder="杈撳叆涔板叆浠?
              autoFocus
              disabled={priceDialogLoading}
            />
            <div className="mt-4 flex gap-2">
              <button onClick={() => setPriceDialog(null)} disabled={priceDialogLoading}
                className="flex-1 rounded-lg border border-[#1D2A42] bg-[#0a1422] py-2.5 text-[13px] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF] transition-colors disabled:opacity-50">
                鍙栨秷
              </button>
              <button onClick={confirmAddWatchlist} disabled={priceDialogLoading}
                className="flex-1 rounded-lg bg-[#4DA3FF] py-2.5 text-[13px] font-semibold text-[#00315b] hover:bg-[#7ddeff] transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                {priceDialogLoading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#00315b] border-t-transparent" /> : null}
                {priceDialogLoading ? "娣诲姞涓?.." : "纭娣诲姞"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function KPI({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  const isBest = label === "浠婃棩鏈€浣?;
  return (
    <div className={`glass card-lift rounded-2xl p-4 ${isBest ? "border border-[rgba(62,230,168,0.2)]" : ""}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[#6E7C93]">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent, boxShadow: `0 0 8px ${accent}` }}></span>
      </div>
      <div className="font-display-numeric text-[20px] sm:text-[26px] truncate" style={{ color: accent }}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-[#9FB0C7]">{sub}</div>
    </div>
  );
}
