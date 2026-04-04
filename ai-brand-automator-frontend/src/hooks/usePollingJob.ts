/**
 * usePollingJob — polls an analysis job while it is in-flight.
 *
 * Uses the lightweight `/quick-status` endpoint (Redis-cached) while the
 * job is "queued" or "running", then fetches the full job detail once a
 * terminal state is reached.  Stops automatically on "completed" / "failed"
 * or when the component unmounts.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getJob, getJobQuickStatus } from '@/lib/orchestration';
import type { AnalysisJob, QuickStatus } from '@/types/orchestration';

interface UsePollingJobOptions {
  /** Polling interval in ms (default 3000). */
  intervalMs?: number;
}

interface UsePollingJobReturn {
  job: AnalysisJob | null;
  /** Lightweight quick-status data updated on every poll cycle. */
  quickStatus: QuickStatus | null;
  isLoading: boolean;
  error: string | null;
  /** Force an immediate re-fetch. */
  refresh: () => void;
}

export function usePollingJob(
  jobId: string | null,
  options: UsePollingJobOptions = {},
): UsePollingJobReturn {
  const { intervalMs = 3000 } = options;

  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [quickStatus, setQuickStatus] = useState<QuickStatus | null>(null);
  const [isLoading, setIsLoading] = useState(!!jobId);
  const [error, setError] = useState<string | null>(null);

  // Track current jobId to avoid stale closures.
  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;

  const fetchFull = useCallback(async () => {
    const id = jobIdRef.current;
    if (!id) return;
    try {
      const data = await getJob(id);
      if (jobIdRef.current === id) {
        setJob(data);
        setError(null);
      }
    } catch (err) {
      if (jobIdRef.current === id) {
        setError(err instanceof Error ? err.message : 'Failed to fetch job');
      }
    } finally {
      if (jobIdRef.current === id) {
        setIsLoading(false);
      }
    }
  }, []);

  // Initial fetch + polling loop using setTimeout to prevent overlapping fetches.
  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setQuickStatus(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      if (cancelled) return;
      const id = jobIdRef.current;
      if (!id) return;

      try {
        const qs = await getJobQuickStatus(id);
        if (cancelled || jobIdRef.current !== id) return;

        setQuickStatus(qs);
        setError(null);
        setIsLoading(false);

        // On terminal state, fetch full job detail and stop polling
        if (qs.status === 'completed' || qs.status === 'failed' || qs.status === 'awaiting_approval') {
          await fetchFull();
          return; // stop polling
        }

        // Schedule next poll
        timer = setTimeout(poll, intervalMs);
      } catch (err) {
        if (!cancelled && jobIdRef.current === id) {
          setError(err instanceof Error ? err.message : 'Failed to fetch status');
          setIsLoading(false);
          // Retry after interval even on error
          timer = setTimeout(poll, intervalMs);
        }
      }
    };

    // Fetch full job state, then immediately poll quick-status so
    // quickStatus is populated without waiting the full interval.
    // This is critical for restored jobs (e.g. page refresh) where
    // components depend on quickStatus to render results.
    (async () => {
      await fetchFull();
      if (!cancelled) {
        await poll();
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, intervalMs, fetchFull]);

  return { job, quickStatus, isLoading, error, refresh: fetchFull };
}
