'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import type { TrendPoint } from '@/types/analytics';

interface TrendChartProps {
  data: TrendPoint[];
  color?: string;
  metricName?: string;
  loading?: boolean;
}

export default function TrendChart({
  data,
  color = '#00F5FF',
  metricName = 'Metric',
  loading,
}: TrendChartProps) {
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

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-medium text-brand-silver mb-4">
        {metricName} Trend
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id={`gradient-${metricName}`} x1="0" y1="0" x2="0" y2="1">
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
            fill={`url(#gradient-${metricName})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
