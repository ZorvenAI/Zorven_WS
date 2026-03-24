import { apiClient } from '@/lib/api';
import type {
  AnalyticsCoverage,
  ComparisonItem,
  DistributionData,
  MetricDefinition,
  Period,
  ScorecardItem,
  TimeRange,
  TrendPoint,
} from '@/types/analytics';

export async function getScorecard(
  range: TimeRange,
  brandContext?: string
): Promise<ScorecardItem[]> {
  const params = new URLSearchParams({ range });
  if (brandContext) params.set('brand_context', brandContext);
  const response = await apiClient.request(`/analytics/scorecard/?${params}`);
  if (!response.ok) throw new Error('Failed to fetch scorecard');
  return response.json();
}

export async function getTrends(
  metric: string,
  range: TimeRange,
  period: Period = 'daily',
  pipelineId?: string,
  brandContext?: string
): Promise<TrendPoint[]> {
  const params = new URLSearchParams({ metric, range, period });
  if (pipelineId) params.set('pipeline_id', pipelineId);
  if (brandContext) params.set('brand_context', brandContext);
  const response = await apiClient.request(`/analytics/trends/?${params}`);
  if (!response.ok) throw new Error('Failed to fetch trends');
  return response.json();
}

export async function getComparison(
  range: TimeRange,
  compare: 'previous' | 'yoy' = 'previous',
  brandContext?: string
): Promise<ComparisonItem[]> {
  const params = new URLSearchParams({ range, compare });
  if (brandContext) params.set('brand_context', brandContext);
  const response = await apiClient.request(
    `/analytics/comparison/?${params}`
  );
  if (!response.ok) throw new Error('Failed to fetch comparison');
  return response.json();
}

export async function getDistribution(
  metric: string,
  range: TimeRange,
  brandContext?: string
): Promise<DistributionData> {
  const params = new URLSearchParams({ metric, range });
  if (brandContext) params.set('brand_context', brandContext);
  const response = await apiClient.request(
    `/analytics/distribution/?${params}`
  );
  if (!response.ok) throw new Error('Failed to fetch distribution');
  return response.json();
}

export async function getMetricDefinitions(): Promise<MetricDefinition[]> {
  const response = await apiClient.request('/analytics/metrics/');
  if (!response.ok) throw new Error('Failed to fetch metric definitions');
  return response.json();
}

export async function getCoverage(
  brandContext?: string
): Promise<AnalyticsCoverage> {
  const params = new URLSearchParams();
  if (brandContext) params.set('brand_context', brandContext);
  const qs = params.toString();
  const response = await apiClient.request(
    `/analytics/coverage/${qs ? `?${qs}` : ''}`
  );
  if (!response.ok) throw new Error('Failed to fetch coverage');
  return response.json();
}
