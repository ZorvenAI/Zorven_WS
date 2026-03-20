'use client';

import { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { getComparison } from '@/lib/analytics';
import type { ComparisonItem, TimeRange } from '@/types/analytics';

interface ComparisonBarsProps {
  range: TimeRange;
}

export default function ComparisonBars({ range }: ComparisonBarsProps) {
  const [data, setData] = useState<ComparisonItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getComparison(range)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [range]);

  if (loading) {
    return (
      <div className="glass-card p-6 animate-pulse">
        <div className="h-4 bg-white/10 rounded w-40 mb-4" />
        <div className="h-64 bg-white/5 rounded" />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="glass-card p-6">
        <p className="text-brand-silver text-sm text-center py-12">
          No comparison data available yet.
        </p>
      </div>
    );
  }

  const chartData = data.map((item) => ({
    name: item.display_name.length > 15
      ? item.display_name.slice(0, 15) + '...'
      : item.display_name,
    current: item.current_avg,
    previous: item.previous_avg,
  }));

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-medium text-brand-silver mb-4">
        Period Comparison
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="name"
            stroke="rgba(255,255,255,0.3)"
            tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }}
            interval={0}
            angle={-20}
            textAnchor="end"
            height={60}
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
          />
          <Legend
            wrapperStyle={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}
          />
          <Bar dataKey="current" name="Current" fill="#00F5FF" radius={[4, 4, 0, 0]} />
          <Bar dataKey="previous" name="Previous" fill="rgba(255,255,255,0.2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
