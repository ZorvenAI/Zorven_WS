'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, BarChart3 } from 'lucide-react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { useAnalytics, useMetricTrend } from '@/hooks/useAnalytics';
import { getComparison, getMetricDefinitions } from '@/lib/analytics';
import type {
  ComparisonItem,
  MetricDefinition,
  Period,
  TimeRange,
} from '@/types/analytics';
import TimeRangePicker from '@/components/analytics/TimeRangePicker';
import KpiScorecard from '@/components/analytics/KpiScorecard';
import TrendChart from '@/components/analytics/TrendChart';
import DistributionGauge from '@/components/analytics/DistributionGauge';
import AnalyticsCoverage from '@/components/analytics/AnalyticsCoverage';

export default function AnalyticsPage() {
  useAuth();

  const [hasMounted, setHasMounted] = useState(false);
  const [range, setRange] = useState<TimeRange>('30d');
  const [period, setPeriod] = useState<Period>('daily');
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);
  const [definitions, setDefinitions] = useState<MetricDefinition[]>([]);
  const [comparison, setComparison] = useState<ComparisonItem[]>([]);

  const { scorecard, coverage, loading } = useAnalytics(range);
  const activeMetric = selectedMetric || (scorecard.length > 0 ? scorecard[0].metric_name : null);
  const { data: trendData, loading: trendLoading } = useMetricTrend(activeMetric, range, period);

  const activeMetricDef = scorecard.find((s) => s.metric_name === activeMetric);

  const fetchDefinitions = useCallback(async () => {
    setHasMounted(true);
    try {
      const defs = await getMetricDefinitions();
      setDefinitions(defs);
    } catch { /* ignore */ }
  }, []);

  const fetchComparison = useCallback(async () => {
    try {
      const data = await getComparison(range);
      setComparison(data);
    } catch {
      setComparison([]);
    }
  }, [range]);

  useEffect(() => {
    fetchDefinitions(); // eslint-disable-line react-hooks/set-state-in-effect
  }, [fetchDefinitions]);

  useEffect(() => {
    fetchComparison(); // eslint-disable-line react-hooks/set-state-in-effect
  }, [fetchComparison]);

  if (!hasMounted) {
    return (
      <div className="min-h-screen bg-brand-midnight flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-50" />

      <div className="relative z-10 max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 mb-6">
          <Link href="/dashboard" className="text-brand-silver hover:text-white transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="flex-1">
            <h1 className="text-3xl font-heading font-bold text-white">
              Workflow Analytics
            </h1>
            <AnalyticsCoverage data={coverage} />
          </div>
          <TimeRangePicker value={range} onChange={setRange} />
        </div>

        {/* Empty state */}
        {!loading && scorecard.length === 0 && (
          <div className="glass-card p-12 text-center">
            <BarChart3 className="h-12 w-12 text-brand-silver/50 mx-auto mb-4" />
            <h2 className="text-lg text-white font-medium mb-2">
              No analytics data yet
            </h2>
            <p className="text-brand-silver text-sm mb-4">
              Run your first workflow to see analytics here
            </p>
            <Link
              href="/dashboard/workflows"
              className="btn-primary inline-block px-4 py-2 rounded-lg text-sm"
            >
              Go to Workflows
            </Link>
          </div>
        )}

        {(loading || scorecard.length > 0) && (
          <div className="space-y-6">
            {/* KPI Scorecard */}
            <KpiScorecard items={scorecard} loading={loading} />

            {/* Metric selector + Period picker */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex gap-2 flex-wrap">
                {(definitions.length > 0 ? definitions : scorecard).map((item) => {
                  const name = 'metric_name' in item ? item.metric_name : '';
                  const display = 'display_name' in item ? item.display_name : '';
                  return (
                    <button
                      key={name}
                      onClick={() => setSelectedMetric(name)}
                      className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                        activeMetric === name
                          ? 'bg-brand-electric/20 text-brand-electric border border-brand-electric/30'
                          : 'bg-white/5 text-brand-silver hover:bg-white/10 border border-transparent'
                      }`}
                    >
                      {display}
                    </button>
                  );
                })}
              </div>
              <div className="inline-flex rounded-lg border border-white/10 bg-white/5 p-1">
                {(['daily', 'weekly', 'monthly'] as Period[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      period === p
                        ? 'bg-brand-electric/20 text-brand-electric'
                        : 'text-brand-silver hover:text-white'
                    }`}
                  >
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Full-width trend chart */}
            <TrendChart
              data={trendData}
              color={activeMetricDef?.color}
              metricName={activeMetricDef?.display_name}
              loading={trendLoading}
            />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Sentiment distribution */}
              <DistributionGauge range={range} />

              {/* Period comparison table */}
              <div className="glass-card p-6">
                <h3 className="text-sm font-medium text-brand-silver mb-4">
                  Period Comparison
                </h3>
                {comparison.length === 0 ? (
                  <p className="text-brand-silver/60 text-sm text-center py-8">
                    No comparison data available
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-brand-silver/60 border-b border-white/5">
                          <th className="text-left py-2 font-medium">Metric</th>
                          <th className="text-right py-2 font-medium">Current</th>
                          <th className="text-right py-2 font-medium">Previous</th>
                          <th className="text-right py-2 font-medium">Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.map((item) => (
                          <tr
                            key={item.metric}
                            className="border-b border-white/5 hover:bg-white/5 cursor-pointer"
                            onClick={() => setSelectedMetric(item.metric)}
                          >
                            <td className="py-2.5 text-white">{item.display_name}</td>
                            <td className="py-2.5 text-right text-white font-medium">
                              {item.current_avg.toFixed(1)}
                            </td>
                            <td className="py-2.5 text-right text-brand-silver">
                              {item.previous_avg.toFixed(1)}
                            </td>
                            <td className={`py-2.5 text-right font-medium ${
                              item.change_pct > 0
                                ? 'text-emerald-400'
                                : item.change_pct < 0
                                  ? 'text-red-400'
                                  : 'text-brand-silver'
                            }`}>
                              {item.change_pct > 0 ? '+' : ''}
                              {item.change_pct.toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
