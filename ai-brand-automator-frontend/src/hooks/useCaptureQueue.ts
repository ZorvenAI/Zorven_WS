'use client';

/**
 * Offline-aware upload queue for photo captures (H-01, AC-4).
 *
 * Simpler than useChunkUploader (discrete photos vs streaming byte ranges).
 * Each enqueued capture is uploaded via uploadCapture(); failures retry with
 * exponential backoff, and an 'online' event flushes the queue when
 * connectivity returns.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { backoffMs } from '@/lib/resumable-upload';
import {
  uploadCapture,
  type CapturedMedia,
  type UsageTag,
} from '@/lib/onboarding-sessions';

interface QueueEntry {
  id: string;
  blob: Blob;
  fileName: string;
  tag: UsageTag;
  sessionId: string;
  attempt: number;
}

export type CaptureQueueStatus = 'idle' | 'uploading' | 'error';

export interface CaptureQueueReturn {
  enqueue: (blob: Blob, tag: UsageTag, fileName?: string) => void;
  captures: CapturedMedia[];
  pending: number;
  status: CaptureQueueStatus;
}

let nextId = 0;

export function useCaptureQueue(sessionId: string | null): CaptureQueueReturn {
  const queue = useRef<QueueEntry[]>([]);
  const draining = useRef(false);
  const [captures, setCaptures] = useState<CapturedMedia[]>([]);
  const [pending, setPending] = useState(0);
  const [status, setStatus] = useState<CaptureQueueStatus>('idle');

  const drain = useCallback(async () => {
    if (draining.current || queue.current.length === 0) return;
    draining.current = true;
    setStatus('uploading');

    while (queue.current.length > 0) {
      const entry = queue.current[0];
      try {
        const file = new File([entry.blob], entry.fileName, {
          type: entry.blob.type || 'image/jpeg',
        });
        const result = await uploadCapture(entry.sessionId, file, entry.tag);
        queue.current.shift();
        setPending(queue.current.length);
        setCaptures((prev) => [...prev, result]);
      } catch {
        entry.attempt += 1;
        setStatus('error');
        const delay = backoffMs(entry.attempt);
        draining.current = false;
        setTimeout(() => {
          void drain();
        }, delay);
        return;
      }
    }

    draining.current = false;
    setStatus('idle');
  }, []);

  const enqueue = useCallback(
    (blob: Blob, tag: UsageTag, fileName?: string) => {
      if (!sessionId) return;
      const entry: QueueEntry = {
        id: String(nextId++),
        blob,
        fileName: fileName ?? `capture-${Date.now()}.jpg`,
        tag,
        sessionId,
        attempt: 0,
      };
      queue.current.push(entry);
      setPending(queue.current.length);
      void drain();
    },
    [sessionId, drain],
  );

  useEffect(() => {
    const handler = () => {
      void drain();
    };
    window.addEventListener('online', handler);
    return () => window.removeEventListener('online', handler);
  }, [drain]);

  return { enqueue, captures, pending, status };
}
