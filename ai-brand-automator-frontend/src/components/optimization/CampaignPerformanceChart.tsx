'use client';

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import type { PerformanceTrendPoint } from '@/lib/optimization';

interface TooltipPayloadEntry {
  color: string;
  name: string;
  value: number | null;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-brand-midnight/95 border border-white/10 rounded-lg p-3 shadow-xl">
      <p className="text-xs font-medium text-brand-silver mb-1.5">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {entry.value !== null ? entry.value : '--'}
        </p>
      ))}
    </div>
  );
}

interface CampaignPerformanceChartProps {
  data: PerformanceTrendPoint[];
  loading?: boolean;
}

export default function CampaignPerformanceChart({
  data,
  loading,
}: CampaignPerformanceChartProps) {
  const hasData = data.length > 0 && data.some(
    (d) => d.cpa !== null || d.ctr !== null || d.roas !== null
  );

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-brand-silver" />
          <h3 className="text-sm font-medium text-white">
            7-Day Performance Trend
          </h3>
        </div>
        <span className="text-xs text-brand-silver/40">
          Updated every optimization tick
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-5 h-5 border-2 border-brand-electric/30 border-t-brand-electric rounded-full animate-spin" />
        </div>
      ) : !hasData ? (
        <div className="flex flex-col items-center justify-center py-12">
          <BarChart3 className="h-10 w-10 text-brand-silver/20 mb-3" />
          <p className="text-sm text-brand-silver/60">
            Performance data will appear after optimization ticks begin
          </p>
          <p className="text-xs text-brand-silver/40 mt-1">
            CPA, CTR, and ROAS trends will be plotted here
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="date"
              stroke="rgba(255,255,255,0.3)"
              tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
            />
            <YAxis
              stroke="rgba(255,255,255,0.3)"
              tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }}
            />
            <Line
              type="monotone"
              dataKey="cpa"
              name="CPA ($)"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="ctr"
              name="CTR (%)"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="roas"
              name="ROAS (x)"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
