'use client';

import { TrendingDown, TrendingUp, Minus } from 'lucide-react';
import type { ScorecardItem } from '@/types/analytics';

interface KpiScorecardProps {
  items: ScorecardItem[];
  loading?: boolean;
}

function formatValue(value: number, unit: string): string {
  if (unit === 'currency') {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
  }
  if (unit === 'percent') return `${value.toFixed(1)}%`;
  if (unit === 'count') return value.toFixed(0);
  return value.toFixed(1);
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'improving') return <TrendingUp className="h-4 w-4 text-emerald-400" />;
  if (trend === 'declining') return <TrendingDown className="h-4 w-4 text-red-400" />;
  return <Minus className="h-4 w-4 text-brand-silver" />;
}

function SparklineChart({ data, color }: { data: number[]; color: string }) {
  if (!data || data.length < 2) return null;

  // Simple SVG sparkline since recharts Sparklines isn't a direct export
  const width = 80;
  const height = 24;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function KpiScorecard({ items, loading }: KpiScorecardProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="glass-card p-4 animate-pulse">
            <div className="h-4 bg-white/10 rounded w-24 mb-3" />
            <div className="h-8 bg-white/10 rounded w-16 mb-2" />
            <div className="h-3 bg-white/10 rounded w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (!items.length) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.slice(0, 8).map((item) => {
        const isGood =
          (item.higher_is_better && item.trend === 'improving') ||
          (!item.higher_is_better && item.trend === 'declining');
        const changeBg = isGood
          ? 'text-emerald-400'
          : item.trend === 'stable'
            ? 'text-brand-silver'
            : 'text-red-400';

        return (
          <div key={item.metric_name} className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-brand-silver truncate">
                {item.display_name}
              </span>
              <TrendIcon trend={item.trend} />
            </div>
            <div className="flex items-end justify-between">
              <div>
                <div className="text-2xl font-bold text-white">
                  {formatValue(item.current_value, item.unit)}
                </div>
                <div className={`text-xs mt-1 ${changeBg}`}>
                  {item.change_pct > 0 ? '+' : ''}
                  {item.change_pct.toFixed(1)}%
                </div>
              </div>
              <SparklineChart data={item.sparkline_data} color={item.color} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
