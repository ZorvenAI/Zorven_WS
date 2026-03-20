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
  const response = await apiClient.request(`/analytics/scorecard/?range=${range}`);
  if (!response.ok) throw new Error('Failed to fetch scorecard');
  return response.json();
}

export async function getTrends(
  metric: string,
  range: TimeRange,
  period: Period = 'daily',
  pipelineId?: string
): Promise<TrendPoint[]> {
  let url = `/analytics/trends/?metric=${metric}&range=${range}&period=${period}`;
  if (pipelineId) url += `&pipeline_id=${pipelineId}`;
  const response = await apiClient.request(url);
  if (!response.ok) throw new Error('Failed to fetch trends');
  return response.json();
}

export async function getComparison(
  range: TimeRange,
  compare: 'previous' | 'yoy' = 'previous'
): Promise<ComparisonItem[]> {
  const response = await apiClient.request(
    `/analytics/comparison/?range=${range}&compare=${compare}`
  );
  if (!response.ok) throw new Error('Failed to fetch comparison');
  return response.json();
}

export async function getDistribution(
  metric: string,
  range: TimeRange
): Promise<DistributionData> {
  const response = await apiClient.request(
    `/analytics/distribution/?metric=${metric}&range=${range}`
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
