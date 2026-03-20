export interface ScorecardItem {
  metric_name: string;
  display_name: string;
  current_value: number;
  previous_value: number | null;
  change_pct: number;
  trend: 'improving' | 'stable' | 'declining';
  sparkline_data: number[];
  unit: string;
  color: string;
  higher_is_better: boolean;
}

export interface TrendPoint {
  period_start: string;
  avg_value: number;
  min_value: number;
  max_value: number;
  sample_count: number;
}

export interface ComparisonItem {
  metric: string;
  display_name: string;
  current_avg: number;
  previous_avg: number;
  change_pct: number;
  trend: string;
}

export interface DistributionData {
  positive_pct: number;
  neutral_pct: number;
  negative_pct: number;
}

export interface AnalyticsCoverage {
  total_jobs: number;
  analytics_jobs: number;
  excluded_jobs: number;
  coverage_pct: number;
}

export interface MetricDefinition {
  metric_name: string;
  display_name: string;
  category: string;
  unit: string;
  value_range_min: number;
  value_range_max: number;
  higher_is_better: boolean;
  chart_color: string;
  display_order: number;
  description: string;
  source_pipelines: string[];
}

export type TimeRange = '7d' | '30d' | '90d' | '1y' | 'custom';
export type Period = 'daily' | 'weekly' | 'monthly';
