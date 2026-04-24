'use client';

import { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { getDistribution } from '@/lib/analytics';
import type { DistributionData, TimeRange } from '@/types/analytics';
import InfoTooltip from '@/components/ui/Tooltip';

interface DistributionGaugeProps {
  range: TimeRange;
  brandContext?: string;
}

function DonutGauge({
  data,
  size,
  strokeWidth,
}: {
  data: DistributionData;
  size: number;
  strokeWidth: number;
}) {
  const center = size / 2;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const positiveLen = (data.positive_pct / 100) * circumference;
  const neutralLen = (data.neutral_pct / 100) * circumference;
  const negativeLen = (data.negative_pct / 100) * circumference;

  const positiveOffset = 0;
  const neutralOffset = -positiveLen;
  const negativeOffset = -(positiveLen + neutralLen);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="rgba(255,255,255,0.05)"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="#10B981"
        strokeWidth={strokeWidth}
        strokeDasharray={`${positiveLen} ${circumference - positiveLen}`}
        strokeDashoffset={positiveOffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
      />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="#F59E0B"
        strokeWidth={strokeWidth}
        strokeDasharray={`${neutralLen} ${circumference - neutralLen}`}
        strokeDashoffset={neutralOffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
      />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="#EF4444"
        strokeWidth={strokeWidth}
        strokeDasharray={`${negativeLen} ${circumference - negativeLen}`}
        strokeDashoffset={negativeOffset}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
      />
    </svg>
  );
}

function SentimentLegend({ data, textSize = 'text-sm' }: { data: DistributionData; textSize?: string }) {
  return (
    <div className={`space-y-2 ${textSize}`}>
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
  );
}

export default function DistributionGauge({ range, brandContext }: DistributionGaugeProps) {
  const [data, setData] = useState<DistributionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const d = await getDistribution('sentiment_positive_pct', range, brandContext);
      setData(d);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [range, brandContext]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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

  return (
    <>
      <div
        className="glass-card p-6 cursor-pointer hover:border-brand-electric/30 hover:bg-white/[0.03] transition-all duration-200"
        onClick={() => setExpanded(true)}
      >
        <InfoTooltip tabIndex={0} text="Breakdown of sentiment polarity from Voice of Customer analysis. Shows what percentage of customer feedback is positive, neutral, or negative. Click to expand.">
          <h3 className="text-sm font-medium text-brand-silver mb-4 cursor-default">
            Sentiment Distribution
          </h3>
        </InfoTooltip>
        <div className="flex items-center justify-center gap-8">
          <DonutGauge data={data} size={130} strokeWidth={12} />
          <SentimentLegend data={data} />
        </div>
      </div>

      {expanded && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setExpanded(false)}
        >
          <div
            className="glass-card border border-white/10 p-6 w-full max-w-lg mx-4 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setExpanded(false)}
              className="absolute top-3 right-3 text-brand-silver/60 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
            <h3 className="text-lg font-bold text-white mb-6">
              Sentiment Distribution
            </h3>
            <div className="flex items-center justify-center gap-12">
              <DonutGauge data={data} size={240} strokeWidth={20} />
              <SentimentLegend data={data} textSize="text-base" />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
