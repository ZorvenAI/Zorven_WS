'use client';

/**
 * useLibraryPolling — polls recordings and captures for the library rail (I-01).
 *
 * Uses setTimeout (not setInterval) to prevent overlapping fetches, matching
 * the usePollingJob pattern. Stops when sessionId is null or on unmount.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  listSessionRecordings,
  listSessionCaptures,
  type RecordingItem,
  type CapturedMedia,
} from '@/lib/onboarding-sessions';

interface UseLibraryPollingReturn {
  recordings: RecordingItem[];
  captures: CapturedMedia[];
  loading: boolean;
}

export function useLibraryPolling(
  sessionId: string | null,
  intervalMs = 5000,
): UseLibraryPollingReturn {
  const [recordings, setRecordings] = useState<RecordingItem[]>([]);
  const [captures, setCaptures] = useState<CapturedMedia[]>([]);
  const [loading, setLoading] = useState(!!sessionId);

  const sessionIdRef = useRef(sessionId);

  const fetchOnce = useCallback(async () => {
    const id = sessionIdRef.current;
    if (!id) return;
    try {
      const [recs, caps] = await Promise.all([
        listSessionRecordings(id),
        listSessionCaptures(id),
      ]);
      if (sessionIdRef.current === id) {
        setRecordings(recs);
        setCaptures(caps);
      }
    } catch {
      // Silent — stale data is better than no data.
    } finally {
      if (sessionIdRef.current === id) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setRecordings([]);
      setCaptures([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      if (cancelled) return;
      await fetchOnce();
      if (!cancelled) {
        timer = setTimeout(poll, intervalMs);
      }
    };

    void poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [sessionId, intervalMs, fetchOnce]);

  return { recordings, captures, loading };
}
