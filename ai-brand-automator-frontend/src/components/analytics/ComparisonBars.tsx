'use client';

import { useCallback, useEffect, useState } from 'react';
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
import { X } from 'lucide-react';
import { getComparison } from '@/lib/analytics';
import type { ComparisonItem, TimeRange } from '@/types/analytics';
import InfoTooltip from '@/components/ui/Tooltip';

interface ComparisonBarsProps {
  range: TimeRange;
  brandContext?: string;
}

function ComparisonBarChart({
  chartData,
  height,
  showFullLabels,
}: {
  chartData: { name: string; fullName: string; current: number; previous: number }[];
  height: number;
  showFullLabels?: boolean;
}) {
  const displayData = showFullLabels
    ? chartData.map((d) => ({ ...d, name: d.fullName }))
    : chartData;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={displayData} barCategoryGap="20%">
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="name"
          stroke="rgba(255,255,255,0.3)"
          tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: showFullLabels ? 11 : 10 }}
          interval={0}
          angle={-20}
          textAnchor="end"
          height={showFullLabels ? 80 : 60}
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
  );
}

export default function ComparisonBars({ range, brandContext }: ComparisonBarsProps) {
  const [data, setData] = useState<ComparisonItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const d = await getComparison(range, 'previous', brandContext);
      setData(d);
    } catch {
      setData([]);
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
    fullName: item.display_name,
    current: item.current_avg,
    previous: item.previous_avg,
  }));

  return (
    <>
      <div
        className="glass-card p-6 cursor-pointer hover:border-brand-electric/30 hover:bg-white/[0.03] transition-all duration-200"
        onClick={() => setExpanded(true)}
      >
        <InfoTooltip text="Compares average metric values between the current period and the previous equivalent period. Taller cyan bars mean the metric improved versus the prior period. Click to expand.">
          <h3 className="text-sm font-medium text-brand-silver mb-4 cursor-default">
            Period Comparison
          </h3>
        </InfoTooltip>
        <ComparisonBarChart chartData={chartData} height={280} />
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
              Period Comparison
            </h3>
            <ComparisonBarChart chartData={chartData} height={500} showFullLabels />
            <div className="mt-4 text-xs text-brand-silver/60 text-center">
              {chartData.length} metrics compared
            </div>
          </div>
        </div>
      )}
    </>
  );
}
