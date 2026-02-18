/**
 * usePollingJob — polls an analysis job while it is in-flight.
 *
 * Fetches the job every `intervalMs` (default 3 s) while status is
 * "queued" or "running".  Stops automatically on "completed" / "failed"
 * or when the component unmounts.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getJob } from '@/lib/orchestration';
import type { AnalysisJob } from '@/types/orchestration';

interface UsePollingJobOptions {
  /** Polling interval in ms (default 3000). */
  intervalMs?: number;
}

interface UsePollingJobReturn {
  job: AnalysisJob | null;
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
  const [isLoading, setIsLoading] = useState(!!jobId);
  const [error, setError] = useState<string | null>(null);

  // Track current jobId to avoid stale closures.
  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;

  const fetchJob = useCallback(async () => {
    const id = jobIdRef.current;
    if (!id) return;
    try {
      const data = await getJob(id);
      // Only update if we are still looking at the same job.
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
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      if (cancelled) return;
      await fetchJob();
      // Schedule next poll only after fetch completes
      if (!cancelled) {
        // Check terminal state via ref to avoid stale closure
        setJob((prev) => {
          if (prev && (prev.status === 'completed' || prev.status === 'failed')) {
            // Terminal state — stop polling
            return prev;
          }
          // Schedule next poll
          timer = setTimeout(poll, intervalMs);
          return prev;
        });
      }
    };

    poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, intervalMs, fetchJob]);

  return { job, isLoading, error, refresh: fetchJob };
}
