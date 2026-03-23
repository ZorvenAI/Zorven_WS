'use client';

import { useState } from 'react';
import { TrendingDown, TrendingUp, Minus, X } from 'lucide-react';
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

function TrendIcon({ trend, size = 'sm' }: { trend: string; size?: 'sm' | 'lg' }) {
  const cls = size === 'lg' ? 'h-6 w-6' : 'h-4 w-4';
  if (trend === 'improving') return <TrendingUp className={`${cls} text-emerald-400`} />;
  if (trend === 'declining') return <TrendingDown className={`${cls} text-red-400`} />;
  return <Minus className={`${cls} text-brand-silver`} />;
}

function SparklineChart({ data, color, width = 80, height = 24 }: { data: number[]; color: string; width?: number; height?: number }) {
  if (!data || data.length < 2) return null;

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

function KpiDetailModal({ item, onClose }: { item: ScorecardItem; onClose: () => void }) {
  const isGood =
    (item.higher_is_better && item.trend === 'improving') ||
    (!item.higher_is_better && item.trend === 'declining');
  const trendColor = isGood
    ? 'text-emerald-400'
    : item.trend === 'stable'
      ? 'text-brand-silver'
      : 'text-red-400';
  const trendLabel = item.trend === 'improving' ? 'Improving' : item.trend === 'declining' ? 'Declining' : 'Stable';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-card border border-white/10 p-6 w-full max-w-md mx-4 relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-brand-silver/60 hover:text-white transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-2 mb-4">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          <h3 className="text-lg font-bold text-white">{item.display_name}</h3>
        </div>

        {/* Value + Trend */}
        <div className="flex items-end gap-4 mb-6">
          <div className="text-4xl font-bold text-white">
            {formatValue(item.current_value, item.unit)}
          </div>
          <div className="flex items-center gap-1.5 pb-1">
            <TrendIcon trend={item.trend} size="lg" />
            <span className={`text-sm font-medium ${trendColor}`}>
              {item.change_pct > 0 ? '+' : ''}
              {item.change_pct.toFixed(1)}% &middot; {trendLabel}
            </span>
          </div>
        </div>

        {/* Sparkline (large) */}
        {item.sparkline_data && item.sparkline_data.length >= 2 && (
          <div className="mb-5 bg-white/5 rounded-lg p-3 border border-white/10">
            <SparklineChart
              data={item.sparkline_data}
              color={item.color}
              width={340}
              height={80}
            />
          </div>
        )}

        {/* Detail rows */}
        <div className="space-y-2 text-sm">
          {item.previous_value != null && (
            <div className="flex justify-between">
              <span className="text-brand-silver/60">Previous Period</span>
              <span className="text-white">{formatValue(item.previous_value, item.unit)}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-brand-silver/60">Change</span>
            <span className={trendColor}>
              {item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-brand-silver/60">Unit</span>
            <span className="text-white capitalize">{item.unit}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-brand-silver/60">Data Points</span>
            <span className="text-white">{item.sparkline_data?.length ?? 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function KpiScorecard({ items, loading }: KpiScorecardProps) {
  const [selectedItem, setSelectedItem] = useState<ScorecardItem | null>(null);

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
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {items.map((item) => {
          const isGood =
            (item.higher_is_better && item.trend === 'improving') ||
            (!item.higher_is_better && item.trend === 'declining');
          const changeBg = isGood
            ? 'text-emerald-400'
            : item.trend === 'stable'
              ? 'text-brand-silver'
              : 'text-red-400';

          return (
            <div
              key={item.metric_name}
              className="glass-card p-4 cursor-pointer hover:border-brand-electric/30 hover:bg-white/[0.03] transition-all duration-200"
              onClick={() => setSelectedItem(item)}
            >
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

      {/* Detail modal */}
      {selectedItem && (
        <KpiDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </>
  );
}
