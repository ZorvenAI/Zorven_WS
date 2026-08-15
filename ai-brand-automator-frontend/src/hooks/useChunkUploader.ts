'use client';

/**
 * Drains the recorder's queue to a resumable GCS session (F-03).
 *
 * Separate from `useMeetingRecorder` on purpose. §4.3 draws durability and
 * analysis as two arrows for a reason the card spells out: "F-06's degraded
 * mode is only cheap because the durability path never depended on STT being
 * up." The recorder produces chunks; this decides where they go; neither knows
 * about the socket F-04 will add.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient } from '@/lib/api';
import {
  ResumableUpload,
  alignedLength,
  backoffMs,
  type UploadTransport,
} from '@/lib/resumable-upload';
import type { RecordedChunk } from '@/hooks/useMeetingRecorder';

export type UploadStatus = 'idle' | 'uploading' | 'delayed' | 'degraded' | 'stopped';

/**
 * The local bound, in minutes of audio.
 *
 * The card is specific that it is minutes rather than megabytes, "because that
 * is the unit the operator-facing message needs" — nobody running a meeting
 * can act on "48 MB". Converted through the measured opus rate rather than a
 * guessed one: Chromium produces ~13.7 KB/s, so ten minutes is about 8 MB,
 * which is well inside what a browser will hold.
 */
export const MAX_LOCAL_MINUTES = 10;
export const BYTES_PER_SECOND = 13742;
export const LOCAL_BOUND_BYTES = MAX_LOCAL_MINUTES * 60 * BYTES_PER_SECOND;

export const BOUND_REACHED_MESSAGE =
  `Recording stopped: ${MAX_LOCAL_MINUTES} minutes of audio are waiting to ` +
  'upload and could not be saved. Check your connection and try again.';

export interface UseChunkUploader {
  status: UploadStatus;
  /** Bytes GCS has acknowledged. The only number that means "safe". */
  uploadedBytes: number;
  /** Bytes held locally, waiting. */
  pendingBytes: number;
  message: string | null;
  /** Call when the recording stops: flushes the tail and closes the object. */
  finalise: () => Promise<void>;
}

export interface UseChunkUploaderOptions {
  recordingId: string | null;
  chunks: RecordedChunk[];
  recording: boolean;
  /** Injected in tests. */
  transport?: UploadTransport;
  /** Called when the local bound is hit, so the recorder can stop (AC-3). */
  onBoundReached?: () => void;
}

interface SessionInfo {
  session_url: string;
  degraded_message: string;
}

export function useChunkUploader({
  recordingId,
  chunks,
  recording,
  transport,
  onBoundReached,
}: UseChunkUploaderOptions): UseChunkUploader {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [uploadedBytes, setUploaded] = useState(0);
  const [pendingBytes, setPending] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  const upload = useRef<ResumableUpload | null>(null);
  const session = useRef<SessionInfo | null>(null);
  /** Chunks accepted from the recorder but not yet acknowledged by GCS. */
  const buffer = useRef<Blob[]>([]);
  const consumed = useRef(0);
  const attempt = useRef(0);
  const busy = useRef(false);
  const halted = useRef(false);

  const openSession = useCallback(async (): Promise<SessionInfo | null> => {
    if (session.current || !recordingId) return session.current;
    try {
      const response = await apiClient.post(
        `/onboarding/recordings/${recordingId}/upload-session/`,
        {},
      );
      if (!response.ok) return null;
      const body = (await response.json()) as SessionInfo;
      session.current = body;
      upload.current = new ResumableUpload(body.session_url, transport);
      return body;
    } catch {
      return null;
    }
  }, [recordingId, transport]);

  /**
   * Take everything new from the recorder's queue.
   *
   * Indexed rather than drained: the recorder owns its array and F-04 will
   * read the same one. Consuming it here would make the two readers race for
   * chunks, and the loser silently misses audio.
   */
  const absorb = useCallback(() => {
    for (let i = consumed.current; i < chunks.length; i += 1) {
      buffer.current.push(chunks[i].blob);
    }
    consumed.current = chunks.length;
    setPending(buffer.current.reduce((total, blob) => total + blob.size, 0));
  }, [chunks]);

  const flush = useCallback(
    async ({ final }: { final: boolean }) => {
      if (busy.current || halted.current) return;
      const active = await openSession();
      if (!active || !upload.current) {
        setStatus('delayed');
        return;
      }

      const held = new Blob(buffer.current);
      // Non-final chunks must be a whole number of 256 KiB units; the
      // remainder waits. GCS rejects a misaligned intermediate PUT outright,
      // and the upload cannot continue afterwards.
      const length = final ? held.size : alignedLength(held.size);
      if (length === 0 && !final) {
        setStatus(status === 'degraded' ? 'degraded' : 'uploading');
        return;
      }

      busy.current = true;
      try {
        const outcome = await upload.current.send(held.slice(0, length), { final });
        if (outcome.ok) {
          const rest = held.slice(length);
          buffer.current = rest.size ? [rest] : [];
          setPending(rest.size);
          setUploaded(outcome.committed);
          attempt.current = 0;
          setStatus(final ? 'idle' : 'uploading');
          setMessage(null);
          return;
        }

        if (!outcome.retryable) {
          setStatus('delayed');
          setMessage(session.current?.degraded_message ?? null);
          return;
        }

        attempt.current += 1;
        // AC-2: "a transient 'Saving delayed' indicator, not an error". The
        // audio is not lost — it is held, and the next attempt sends it.
        setStatus(attempt.current > 2 ? 'degraded' : 'delayed');
        if (attempt.current > 2) {
          // AC-3: the message comes from the breaker config the server
          // serves, never a string typed into this component.
          setMessage(session.current?.degraded_message ?? null);
        }
      } finally {
        busy.current = false;
      }
    },
    [openSession, status],
  );

  // Absorb whatever the recorder has produced, and enforce the bound.
  useEffect(() => {
    absorb();
    if (halted.current) return;
    const held = buffer.current.reduce((total, blob) => total + blob.size, 0);
    if (held >= LOCAL_BOUND_BYTES) {
      // AC-3: "when the local bound is reached, recording stops gracefully
      // with an explicit message rather than silently discarding audio". The
      // buffer is kept — dropping it is the one behaviour the criterion rules
      // out — and the recorder is asked to stop.
      halted.current = true;
      setStatus('stopped');
      setMessage(BOUND_REACHED_MESSAGE);
      onBoundReached?.();
    }
  }, [absorb, onBoundReached]);

  // Retry on a cadence while there is anything to send.
  useEffect(() => {
    if (!recording || halted.current) return;
    const delay = attempt.current > 0 ? backoffMs(attempt.current) : ALIGN_INTERVAL_MS;
    const timer = setTimeout(() => void flush({ final: false }), delay);
    return () => clearTimeout(timer);
  }, [recording, flush, pendingBytes, uploadedBytes, status]);

  const finalise = useCallback(async () => {
    absorb();
    await flush({ final: true });
  }, [absorb, flush]);

  return { status, uploadedBytes, pendingBytes, message, finalise };
}

/**
 * How often a flush is attempted while recording.
 *
 * AC-1 asks for thirty seconds of audio per append. At Chromium's measured
 * ~13.7 KB/s that is about 403 KiB — comfortably over the 256 KiB alignment
 * floor, so a thirty-second cadence produces one or two whole units each time
 * with a small remainder carried forward.
 */
export const ALIGN_INTERVAL_MS = 30_000;
