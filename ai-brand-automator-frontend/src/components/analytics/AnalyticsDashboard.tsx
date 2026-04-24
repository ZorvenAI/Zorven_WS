'use client';

import { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { useAnalytics, useMetricTrend } from '@/hooks/useAnalytics';
import { useBrandContext } from '@/hooks/useBrandContext';
import type { TimeRange } from '@/types/analytics';
import TimeRangePicker from './TimeRangePicker';
import KpiScorecard from './KpiScorecard';
import TrendChart from './TrendChart';
import ComparisonBars from './ComparisonBars';
import DistributionGauge from './DistributionGauge';
import AnalyticsCoverage from './AnalyticsCoverage';
import BrandContextSelector from '@/components/brand/BrandContextSelector';
import Tooltip from '@/components/ui/Tooltip';

export default function AnalyticsDashboard() {
  const [range, setRange] = useState<TimeRange>('30d');
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);
  const { activeBrand } = useBrandContext();
  // Don't filter when "parent" is selected — show all metrics (aggregate view)
  const brandContext =
    activeBrand?.brand_context_id && activeBrand.brand_context_id !== 'parent'
      ? activeBrand.brand_context_id
      : undefined;

  const { scorecard, coverage, loading, error } = useAnalytics(
    range,
    brandContext
  );
  const { data: trendData, loading: trendLoading } = useMetricTrend(
    selectedMetric || (scorecard.length > 0 ? scorecard[0].metric_name : null),
    range,
    'daily',
    brandContext
  );

  const activeMetric = selectedMetric || (scorecard.length > 0 ? scorecard[0] : null);
  const activeMetricDef = scorecard.find(
    (s) => s.metric_name === (typeof activeMetric === 'string' ? activeMetric : activeMetric?.metric_name)
  );

  if (error) {
    return null; // Silently fail on dashboard — analytics is non-critical
  }

  // Empty state
  if (!loading && scorecard.length === 0) {
    return (
      <div className="glass-card p-8 text-center">
        <BarChart3 className="h-10 w-10 text-brand-silver/50 mx-auto mb-3" />
        <p className="text-brand-silver text-sm">
          Run your first workflow to see analytics
        </p>
        <a
          href="/dashboard/workflows"
          className="text-brand-electric text-sm hover:underline mt-2 inline-block"
        >
          Go to Workflows
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Tooltip tabIndex={0} text="Aggregated KPIs extracted from completed workflow executions. Metrics are computed from pipeline results across discovery, brand strategy, content, and campaign workflows.">
            <h2 className="text-xl font-heading font-semibold text-white cursor-default">
              Workflow Analytics
            </h2>
          </Tooltip>
          <AnalyticsCoverage data={coverage} />
        </div>
        <div className="flex items-center gap-3">
          <BrandContextSelector />
          <TimeRangePicker value={range} onChange={setRange} />
          <Tooltip text="Open the full analytics page with expanded charts, period selectors, and detailed metric breakdowns.">
            <a
              href="/dashboard/analytics"
              className="text-xs text-brand-electric hover:underline"
            >
              View All
            </a>
          </Tooltip>
        </div>
      </div>

      <KpiScorecard items={scorecard} loading={loading} />

      {scorecard.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {scorecard.slice(0, 6).map((item) => (
            <button
              key={item.metric_name}
              onClick={() => setSelectedMetric(item.metric_name)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                (selectedMetric || scorecard[0]?.metric_name) === item.metric_name
                  ? 'bg-brand-electric/20 text-brand-electric border border-brand-electric/30'
                  : 'bg-white/5 text-brand-silver hover:bg-white/10 border border-transparent'
              }`}
            >
              {item.display_name}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TrendChart
          data={trendData}
          color={activeMetricDef?.color}
          metricName={activeMetricDef?.display_name}
          loading={trendLoading}
        />
        <ComparisonBars range={range} brandContext={brandContext} />
      </div>

      <DistributionGauge range={range} brandContext={brandContext} />
    </div>
  );
}
