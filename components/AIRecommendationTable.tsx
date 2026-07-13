'use client';

import { useState } from 'react';
import Link from 'next/link';

interface Stock {
  rank: number;
  symbol: string;
  name: string;
  score: number;
  upProbability: number;
  mainForceIntent: string;
  risk: 'low' | 'medium' | 'high';
  price: number;
  change: number;
  changePercent: number;
}

interface AIRecommendationTableProps {
  stocks: Stock[];
  onRefresh?: () => void;
  loading?: boolean;
}

export default function AIRecommendationTable({ stocks, onRefresh, loading }: AIRecommendationTableProps) {
  const [filter, setFilter] = useState<'all' | 'us' | 'cn'>('all');
  const [sortBy, setSortBy] = useState<'score' | 'probability' | 'risk'>('score');

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'low': return 'text-[#3EE6A8]';
      case 'medium': return 'text-[#F5C451]';
      case 'high': return 'text-[#FF5D5D]';
      default: return 'text-[#9FB0C7]';
    }
  };

  const getRiskBadge = (risk: string) => {
    switch (risk) {
      case 'low': return 'bg-[#3EE6A8]/10 text-[#3EE6A8] border-[#3EE6A8]/30';
      case 'medium': return 'bg-[#F5C451]/10 text-[#F5C451] border-[#F5C451]/30';
      case 'high': return 'bg-[#FF5D5D]/10 text-[#FF5D5D] border-[#FF5D5D]/30';
      default: return 'bg-[#9FB0C7]/10 text-[#9FB0C7] border-[#9FB0C7]/30';
    }
  };

  const filteredStocks = stocks.filter(stock => {
    if (filter === 'all') return true;
    if (filter === 'us') return /^[A-Z]+$/.test(stock.symbol);
    if (filter === 'cn') return /^\d+$/.test(stock.symbol);
    return true;
  });

  const sortedStocks = [...filteredStocks].sort((a, b) => {
    switch (sortBy) {
      case 'score': return b.score - a.score;
      case 'probability': return b.upProbability - a.upProbability;
      case 'risk': {
        const riskOrder = { low: 1, medium: 2, high: 3 };
        return riskOrder[a.risk] - riskOrder[b.risk];
      }
      default: return 0;
    }
  });

  return (
    <div className="space-y-4">
      {/* Header with filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-[#4DA3FF]" style={{ fontSize: 28 }}>track_changes</span>
          <h2 className="text-2xl font-bold">AI 推荐股票 Top 20</h2>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Market filter */}
          <div className="flex items-center gap-2 p-1 rounded-lg glass border border-[#1D2A42]">
            {[
              { value: 'all', label: '全部' },
              { value: 'us', label: '美股' },
              { value: 'cn', label: 'A股' },
            ].map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setFilter(value as any)}
                className={`px-3 py-1.5 text-sm rounded transition-all ${
                  filter === value
                    ? 'bg-gradient-to-r from-[#4DA3FF] to-[#35e0a3] text-[#0a1422] font-bold'
                    : 'text-[#9FB0C7] hover:text-[#EAF2FF]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Sort by */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-3 py-1.5 rounded-lg glass border border-[#1D2A42] text-sm text-[#EAF2FF] cursor-pointer hover:border-[#4DA3FF]/50 transition-all bg-[#0C1728]"
          >
            <option value="score">按评分排序</option>
            <option value="probability">按涨概率排序</option>
            <option value="risk">按风险排序</option>
          </select>

          {/* Refresh button */}
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg glass border border-[#1D2A42] text-[#4DA3FF] hover:border-[#4DA3FF] transition-all disabled:opacity-50"
            >
              <span className="material-icons text-sm">refresh</span>
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-2xl border border-[#1D2A42]">
        <table className="w-full">
          <thead className="glass border-b border-[#1D2A42]">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">排名</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">股票代码</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">名称</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">评分</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">涨概率</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">主力意图</th>
              <th className="px-4 py-3 text-center text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">风险</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">价格</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">涨跌幅</th>
              <th className="px-4 py-3 text-center text-xs font-bold text-[#9FB0C7] uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="bg-[#0C1728]/50 divide-y divide-[#1D2A42]">
            {loading ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center">
                  <div className="flex items-center justify-center gap-2">
                    <span className="material-icons animate-spin text-[#4DA3FF]">autorenew</span>
                    <span className="text-[#9FB0C7]">加载中...</span>
                  </div>
                </td>
              </tr>
            ) : sortedStocks.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-[#9FB0C7]">
                  暂无推荐股票
                </td>
              </tr>
            ) : (
              sortedStocks.map((stock) => (
                <tr key={stock.symbol} className="hover:bg-[#101C30] transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full glass border border-[#1D2A42] font-bold text-sm text-[#4DA3FF]">
                      {stock.rank}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono font-bold text-[#4DA3FF]">{stock.symbol}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm">{stock.name}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <div className="w-12 h-2 bg-[#0a1422] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-800"
                          style={{ 
                            width: `${stock.score}%`,
                            background: 'linear-gradient(90deg, #4DA3FF, #35e0a3)'
                          }}
                        />
                      </div>
                      <span className="font-bold text-[#4DA3FF]">{stock.score}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-bold text-[#35e0a3]">{stock.upProbability}%</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-[#9FB0C7]">{stock.mainForceIntent}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 text-xs rounded-full border ${getRiskBadge(stock.risk)}`}>
                      {stock.risk === 'low' ? '低' : stock.risk === 'medium' ? '中' : '高'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-mono">${stock.price.toFixed(2)}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={stock.changePercent >= 0 ? 'text-[#3EE6A8]' : 'text-[#FF5D5D]'}>
                      {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Link
                      href={`/stock/${stock.symbol}`}
                      className="px-3 py-1.5 text-sm rounded-lg glass border border-[#4DA3FF]/30 text-[#4DA3FF] hover:border-[#4DA3FF] transition-all"
                    >
                      详情
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
