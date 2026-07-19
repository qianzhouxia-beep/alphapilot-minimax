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

  const getRiskBadge = (risk: string) => {
    switch (risk) {
      case 'low':
        return 'bg-status-success/10 text-status-success border-status-success/30';
      case 'medium':
        return 'bg-status-warning/10 text-status-warning border-status-warning/30';
      case 'high':
        return 'bg-status-danger/10 text-status-danger border-status-danger/30';
      default:
        return 'bg-border-subtle text-text-tertiary border-border-subtle';
    }
  };

  const filteredStocks = stocks.filter((stock) => {
    if (filter === 'all') return true;
    if (filter === 'us') return /^[A-Z]+$/.test(stock.symbol);
    if (filter === 'cn') return /^\d+$/.test(stock.symbol);
    return true;
  });

  const sortedStocks = [...filteredStocks].sort((a, b) => {
    switch (sortBy) {
      case 'score':
        return b.score - a.score;
      case 'probability':
        return b.upProbability - a.upProbability;
      case 'risk': {
        const riskOrder = { low: 1, medium: 2, high: 3 };
        return riskOrder[a.risk] - riskOrder[b.risk];
      }
      default:
        return 0;
    }
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <h2 className="text-2xl font-bold text-text-primary tracking-tight">AI 推荐股票 Top 20</h2>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 p-1 rounded-xl border border-border-subtle bg-surface-card shadow-sm">
            {[
              { value: 'all', label: '全部' },
              { value: 'us', label: '美股' },
              { value: 'cn', label: 'A股' },
            ].map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value as typeof filter)}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-purple-primary/40 ${
                  filter === value
                    ? 'bg-purple-light text-purple-primary font-semibold'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="px-3 py-1.5 rounded-xl border border-border-subtle bg-surface-card text-sm text-text-primary cursor-pointer focus-visible:ring-2 focus-visible:ring-purple-primary/40"
          >
            <option value="score">按评分排序</option>
            <option value="probability">按涨概率排序</option>
            <option value="risk">按风险排序</option>
          </select>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="px-3 py-1.5 rounded-xl border border-border-subtle bg-surface-card text-purple-primary hover:bg-purple-light transition-colors disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-purple-primary/40"
            >
              刷新
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border-subtle bg-surface-card shadow-sm">
        <table className="w-full">
          <thead className="border-b border-border-subtle bg-bg-tertiary/80">
            <tr>
              {['排名', '股票代码', '名称', '信心分', '涨概率', '主力意图', '风险', '价格', '涨跌幅', '操作'].map(
                (h) => (
                  <th
                    key={h}
                    className={`px-4 py-3 text-xs font-semibold text-text-tertiary uppercase tracking-wider ${
                      ['信心分', '涨概率', '价格', '涨跌幅'].includes(h) ? 'text-right' : h === '风险' || h === '操作' ? 'text-center' : 'text-left'
                    }`}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {loading ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-text-secondary">
                  加载中...
                </td>
              </tr>
            ) : sortedStocks.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-text-tertiary">
                  暂无推荐股票
                </td>
              </tr>
            ) : (
              sortedStocks.map((stock) => (
                <tr key={stock.symbol} className="hover:bg-purple-light/40 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full border border-border-subtle bg-bg-tertiary font-bold text-sm text-purple-primary">
                      {stock.rank}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-text-secondary">{stock.symbol}</td>
                  <td className="px-4 py-3 text-sm font-medium text-text-primary">{stock.name}</td>
                  <td className="px-4 py-3 text-right text-sm font-semibold text-purple-primary">
                    {Math.min(99, Math.max(75, Math.round(stock.score * 45 + 75)))}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-text-secondary">
                    {(stock.upProbability * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-3 text-sm text-text-secondary">{stock.mainForceIntent}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] border ${getRiskBadge(stock.risk)}`}>
                      {stock.risk}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-sm font-mono text-text-primary">
                    {stock.price.toFixed(2)}
                  </td>
                  <td
                    className={`px-4 py-3 text-right text-sm font-semibold ${
                      stock.changePercent >= 0 ? 'text-red-negative' : 'text-green-positive'
                    }`}
                  >
                    {stock.changePercent >= 0 ? '+' : ''}
                    {stock.changePercent.toFixed(2)}%
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Link
                      href={`/cn/stock?symbol=${stock.symbol}`}
                      className="text-[12px] font-medium text-purple-primary hover:underline cursor-pointer"
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
