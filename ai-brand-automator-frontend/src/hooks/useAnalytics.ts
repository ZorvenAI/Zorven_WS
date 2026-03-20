'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  getCoverage,
  getScorecard,
  getTrends,
} from '@/lib/analytics';
import type {
  AnalyticsCoverage,
  Period,
  ScorecardItem,
  TimeRange,
  TrendPoint,
} from '@/types/analytics';

export function useAnalytics(range: TimeRange) {
  const [scorecard, setScorecard] = useState<ScorecardItem[]>([]);
  const [coverage, setCoverage] = useState<AnalyticsCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [scorecardData, coverageData] = await Promise.all([
        getScorecard(range),
        getCoverage(),
      ]);
      setScorecard(scorecardData);
      setCoverage(coverageData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { scorecard, coverage, loading, error, refetch: fetchData };
}

export function useMetricTrend(
  metric: string | null,
  range: TimeRange,
  period: Period = 'daily'
) {
  const [data, setData] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!metric) return;
    setLoading(true);
    setError(null);
    try {
      const trendData = await getTrends(metric, range, period);
      setData(trendData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trend data');
    } finally {
      setLoading(false);
    }
  }, [metric, range, period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}
