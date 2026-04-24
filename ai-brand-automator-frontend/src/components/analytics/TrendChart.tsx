'use client';

import { useState } from 'react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import { X } from 'lucide-react';
import type { TrendPoint } from '@/types/analytics';
import InfoTooltip from '@/components/ui/Tooltip';

interface TrendChartProps {
  data: TrendPoint[];
  color?: string;
  metricName?: string;
  loading?: boolean;
}

function TrendAreaChart({
  chartData,
  color,
  metricName,
  height,
  gradientId,
}: {
  chartData: { date: string; avg_value: number }[];
  color: string;
  metricName: string;
  height: number;
  gradientId: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
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
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '8px',
            color: '#fff',
          }}
          formatter={(value) => [Number(value).toFixed(2), 'Avg']}
        />
        <Area
          type="monotone"
          dataKey="avg_value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default function TrendChart({
  data,
  color = '#00F5FF',
  metricName = 'Metric',
  loading,
}: TrendChartProps) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="glass-card p-6 animate-pulse">
        <div className="h-4 bg-white/10 rounded w-32 mb-4" />
        <div className="h-64 bg-white/5 rounded" />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="glass-card p-6">
        <p className="text-brand-silver text-sm text-center py-12">
          No trend data available for this period.
        </p>
      </div>
    );
  }

  const chartData = data.map((point) => ({
    ...point,
    date: new Date(point.period_start).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }));

  const safeMetric = metricName?.replace(/[^a-zA-Z0-9_-]/g, '_') ?? 'metric';

  return (
    <>
      <div
        className="glass-card p-6 cursor-pointer hover:border-brand-electric/30 hover:bg-white/[0.03] transition-all duration-200"
        onClick={() => setExpanded(true)}
      >
        <InfoTooltip tabIndex={0} text={`Shows how ${metricName} has changed over the selected time range. Each point represents the average value for that period. Click to expand for a larger view.`}>
          <h3 className="text-sm font-medium text-brand-silver mb-4 cursor-default">
            {metricName} Trend
          </h3>
        </InfoTooltip>
        <TrendAreaChart
          chartData={chartData}
          color={color}
          metricName={metricName}
          height={280}
          gradientId={`gradient-${safeMetric}`}
        />
      </div>

      {expanded && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setExpanded(false)}
        >
          <div
            className="glass-card border border-white/10 p-6 w-full max-w-4xl mx-4 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setExpanded(false)}
              className="absolute top-3 right-3 text-brand-silver/60 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
            <h3 className="text-lg font-bold text-white mb-4">
              {metricName} Trend
            </h3>
            <TrendAreaChart
              chartData={chartData}
              color={color}
              metricName={metricName}
              height={500}
              gradientId={`gradient-${safeMetric}-modal`}
            />
            <div className="mt-4 text-xs text-brand-silver/60 text-center">
              {chartData.length} data points
            </div>
          </div>
        </div>
      )}
    </>
  );
}
