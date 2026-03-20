'use client';

import { useEffect, useState } from 'react';
import { getDistribution } from '@/lib/analytics';
import type { DistributionData, TimeRange } from '@/types/analytics';

interface DistributionGaugeProps {
  range: TimeRange;
}

export default function DistributionGauge({ range }: DistributionGaugeProps) {
  const [data, setData] = useState<DistributionData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDistribution('sentiment_positive_pct', range)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [range]);

  if (loading) {
    return (
      <div className="glass-card p-6 animate-pulse">
        <div className="h-4 bg-white/10 rounded w-32 mb-4" />
        <div className="h-32 bg-white/5 rounded" />
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const total = data.positive_pct + data.neutral_pct + data.negative_pct;
  if (total === 0) return null;

  // Donut-style gauge using SVG
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const positiveLen = (data.positive_pct / 100) * circumference;
  const neutralLen = (data.neutral_pct / 100) * circumference;
  const negativeLen = (data.negative_pct / 100) * circumference;

  const positiveOffset = 0;
  const neutralOffset = -positiveLen;
  const negativeOffset = -(positiveLen + neutralLen);

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-medium text-brand-silver mb-4">
        Sentiment Distribution
      </h3>
      <div className="flex items-center justify-center gap-8">
        <svg width="130" height="130" viewBox="0 0 130 130">
          <circle
            cx="65"
            cy="65"
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="12"
          />
          <circle
            cx="65"
            cy="65"
            r={radius}
            fill="none"
            stroke="#10B981"
            strokeWidth="12"
            strokeDasharray={`${positiveLen} ${circumference - positiveLen}`}
            strokeDashoffset={positiveOffset}
            strokeLinecap="round"
            transform="rotate(-90 65 65)"
          />
          <circle
            cx="65"
            cy="65"
            r={radius}
            fill="none"
            stroke="#F59E0B"
            strokeWidth="12"
            strokeDasharray={`${neutralLen} ${circumference - neutralLen}`}
            strokeDashoffset={neutralOffset}
            strokeLinecap="round"
            transform="rotate(-90 65 65)"
          />
          <circle
            cx="65"
            cy="65"
            r={radius}
            fill="none"
            stroke="#EF4444"
            strokeWidth="12"
            strokeDasharray={`${negativeLen} ${circumference - negativeLen}`}
            strokeDashoffset={negativeOffset}
            strokeLinecap="round"
            transform="rotate(-90 65 65)"
          />
        </svg>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <span className="text-brand-silver">Positive</span>
            <span className="text-white font-medium ml-auto">{data.positive_pct.toFixed(1)}%</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-amber-500" />
            <span className="text-brand-silver">Neutral</span>
            <span className="text-white font-medium ml-auto">{data.neutral_pct.toFixed(1)}%</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-brand-silver">Negative</span>
            <span className="text-white font-medium ml-auto">{data.negative_pct.toFixed(1)}%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
