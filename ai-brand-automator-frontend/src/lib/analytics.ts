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

export async function getScorecard(range: TimeRange): Promise<ScorecardItem[]> {
  const params = new URLSearchParams({ range });
  const response = await apiClient.request(`/analytics/scorecard/?${params}`);
  if (!response.ok) throw new Error('Failed to fetch scorecard');
  return response.json();
}

export async function getTrends(
  metric: string,
  range: TimeRange,
  period: Period = 'daily',
  pipelineId?: string
): Promise<TrendPoint[]> {
  const params = new URLSearchParams({ metric, range, period });
  if (pipelineId) params.set('pipeline_id', pipelineId);
  const response = await apiClient.request(`/analytics/trends/?${params}`);
  if (!response.ok) throw new Error('Failed to fetch trends');
  return response.json();
}

export async function getComparison(
  range: TimeRange,
  compare: 'previous' | 'yoy' = 'previous'
): Promise<ComparisonItem[]> {
  const params = new URLSearchParams({ range, compare });
  const response = await apiClient.request(
    `/analytics/comparison/?${params}`
  );
  if (!response.ok) throw new Error('Failed to fetch comparison');
  return response.json();
}

export async function getDistribution(
  metric: string,
  range: TimeRange
): Promise<DistributionData> {
  const params = new URLSearchParams({ metric, range });
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

export async function getCoverage(): Promise<AnalyticsCoverage> {
  const response = await apiClient.request('/analytics/coverage/');
  if (!response.ok) throw new Error('Failed to fetch coverage');
  return response.json();
}
