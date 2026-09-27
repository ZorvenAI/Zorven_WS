'use client';

/**
 * Drains the recorder's queue into resumable GCS sessions (F-03, O-07).
 *
 * Separate from `useMeetingRecorder` on purpose. §4.3 draws durability and
 * analysis as two arrows for the reason the card spells out: "F-06's degraded
 * mode is only cheap because the durability path never depended on STT being
 * up." The recorder produces chunks; this decides where they go; neither knows
 * about the socket F-04 added.
 *
 * O-07 makes the destination per-mic. One stream per microphone, each with its
 * own resumable session, buffer, backoff and local bound — because the mics are
 * the only reason the transcript can name a speaker, and concatenating two of
 * them into one object produces bytes no decoder will accept. Before this story
 * the hook absorbed every chunk regardless of which mic produced it, so a
 * two-mic meeting uploaded one interleaved, unplayable object.
 *
 * A single-mic recording is one stream that sends no `stream_index`, which is
 * the pre-O-07 request unchanged.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiClient } from '@/lib/api';
import {
  ResumableUpload,
  alignedLength,
  backoffMs,
  type UploadTransport,
} from '@/lib/resumable-upload';
import type React from 'react';

export type UploadStatus = 'idle' | 'uploading' | 'delayed' | 'degraded' | 'stopped';

/**
 * The local bound, in minutes of audio.
 *
 * The card is specific that it is minutes rather than megabytes, "because that
 * is the unit the operator-facing message needs" — nobody running a meeting
 * can act on "48 MB". Converted through a measured opus rate rather than a
 * guessed one: Chromium produces ~13.7 KB/s, so ten minutes is about 8 MB,
 * well inside what a browser will hold.
 *
 * O-07 AC-2 applies it per stream. Each mic holds its own ten minutes: the
 * limit exists because a browser can only buffer so much per object, and two
 * mics sharing one allowance would halve the tolerance of every participant.
 */
export const MAX_LOCAL_MINUTES = 10;
export const BYTES_PER_SECOND = 13742;
export const LOCAL_BOUND_BYTES = MAX_LOCAL_MINUTES * 60 * BYTES_PER_SECOND;

export const BOUND_REACHED_MESSAGE =
  `Recording stopped: ${MAX_LOCAL_MINUTES} minutes of audio are waiting to ` +
  'upload and could not be saved. Check your connection and try again.';

/**
 * The key for a recording with no per-mic streams.
 *
 * Not a stream index: O-03 addresses streams in one byte, so 0–255 are all
 * real. A recording in this mode sends no `stream_index` at all.
 */
const LEGACY_STREAM = -1;

/** What the caller sees about one mic's upload. */
export interface StreamUploadState {
  streamIndex: number;
  status: UploadStatus;
  uploadedBytes: number;
  pendingBytes: number;
}

export interface UseChunkUploader {
  /** Worst-of across streams: one meeting has one operator-facing status. */
  status: UploadStatus;
  /** Bytes GCS has acknowledged, summed. The only number that means "safe". */
  uploadedBytes: number;
  /** Bytes held locally, waiting, summed. */
  pendingBytes: number;
  message: string | null;
  /** Per-mic detail. One entry for a single-mic recording. */
  streams: StreamUploadState[];
  /** Call when the recording stops: flushes every tail and closes each object. */
  finalise: () => Promise<void>;
}

/** The subset of a recorder chunk this hook needs. */
interface UploadableChunk {
  blob: Blob;
  streamIndex?: number;
}

export interface UseChunkUploaderOptions {
  recordingId: string | null;
  chunksRef: React.RefObject<readonly UploadableChunk[]>;
  chunkCount: number;
  recording: boolean;
  /**
   * One entry per mic (O-07). Omitted or empty means single-stream, which
   * uploads exactly as it did before this story.
   */
  streams?: readonly { streamIndex: number }[];
  /** Injected in tests. */
  transport?: UploadTransport;
  /** Called when a local bound is hit, so the recorder can stop (AC-3). */
  onBoundReached?: () => void;
}

interface SessionInfo {
  session_url: string;
  degraded_message: string;
}

/** Everything one stream needs to upload independently (AC-3). */
interface StreamMachinery {
  upload: ResumableUpload | null;
  session: SessionInfo | null;
  /** Chunks accepted from the recorder but not yet acknowledged by GCS. */
  buffer: Blob[];
  attempt: number;
  busy: boolean;
  halted: boolean;
  /** Epoch ms before which no non-final flush should be attempted. */
  nextAttemptAt: number;
  /** The append in flight, so a close can wait for it rather than skip (AC-4). */
  inflight: Promise<void> | null;
}

function blankStream(key: number): StreamUploadState {
  return {
    streamIndex: key,
    status: 'idle',
    uploadedBytes: 0,
    pendingBytes: 0,
  };
}

function newMachinery(): StreamMachinery {
  return {
    upload: null,
    session: null,
    buffer: [],
    attempt: 0,
    busy: false,
    halted: false,
    nextAttemptAt: 0,
    inflight: null,
  };
}

/** Worst-of precedence for the aggregate indicator. */
const STATUS_RANK: Record<UploadStatus, number> = {
  idle: 0,
  uploading: 1,
  delayed: 2,
  degraded: 3,
  stopped: 4,
};

export function useChunkUploader({
  recordingId,
  chunksRef,
  chunkCount,
  recording,
  streams,
  transport,
  onBoundReached,
}: UseChunkUploaderOptions): UseChunkUploader {
  const keys = useMemo(() => {
    if (!streams || streams.length === 0) return [LEGACY_STREAM];
    return streams.map((s) => s.streamIndex);
  }, [streams]);

  const [perStream, setPerStream] = useState<Record<number, StreamUploadState>>({});
  const [message, setMessage] = useState<string | null>(null);

  /**
   * The active keys, readable from a long-lived interval.
   *
   * The cadence effect must not depend on `keys` identity, or a caller passing
   * a fresh `streams` array each render would re-create the interval before it
   * could ever fire — the same defect the effect's own comment describes.
   */
  const keysRef = useRef(keys);
  keysRef.current = keys;

  const machinery = useRef<Map<number, StreamMachinery>>(new Map());
  /**
   * One cursor over the shared chunk array, not one per stream.
   *
   * The recorder appends every mic's chunks to the same array, so a single
   * pass routing each chunk to its own buffer cannot drop or duplicate one.
   * Per-stream cursors would each have to re-scan the whole array and agree
   * about where they stopped.
   */
  const consumed = useRef(0);

  const machineryFor = useCallback((key: number): StreamMachinery => {
    let state = machinery.current.get(key);
    if (!state) {
      state = newMachinery();
      machinery.current.set(key, state);
    }
    return state;
  }, []);

  /**
   * Update one stream's reported state, bailing out when nothing changed.
   *
   * The bail-out is load-bearing, not an optimisation. `absorb` patches every
   * stream on every pass, and returning a fresh object each time would re-render
   * on each pass; any caller whose `chunksRef` identity is not stable then has
   * its absorb effect re-run, patch again, and render again without end. The
   * pre-O-07 hook got this for free by storing a number, which React compares
   * with `Object.is` before scheduling.
   */
  const patch = useCallback((key: number, next: Partial<StreamUploadState>) => {
    setPerStream((prev) => {
      const base = prev[key] ?? blankStream(key);
      const merged = { ...base, ...next };
      if (
        base.status === merged.status &&
        base.uploadedBytes === merged.uploadedBytes &&
        base.pendingBytes === merged.pendingBytes &&
        prev[key] !== undefined
      ) {
        return prev;
      }
      return { ...prev, [key]: merged };
    });
  }, []);

  const openSession = useCallback(
    async (key: number): Promise<SessionInfo | null> => {
      const state = machineryFor(key);
      if (state.session || !recordingId) return state.session;
      try {
        const response = await apiClient.post(
          `/onboarding/recordings/${recordingId}/upload-session/`,
          // The legacy stream sends no stream_index, so the server takes the
          // single-stream path it always took.
          key === LEGACY_STREAM ? {} : { stream_index: key },
        );
        if (!response.ok) return null;
        const body = (await response.json()) as SessionInfo;
        state.session = body;
        state.upload = new ResumableUpload(body.session_url, transport);
        return body;
      } catch {
        return null;
      }
    },
    [recordingId, transport, machineryFor],
  );

  /**
   * Take everything new from the recorder's queue, routing by mic.
   *
   * Indexed rather than drained: the recorder owns its array and F-04 reads
   * the same one. Consuming it here would make the two readers race for
   * chunks, and the loser silently misses audio.
   */
  const absorb = useCallback(() => {
    const arr = chunksRef.current ?? [];
    const legacy = keys.length === 1 && keys[0] === LEGACY_STREAM;
    for (let i = consumed.current; i < arr.length; i += 1) {
      const chunk = arr[i];
      let key = legacy ? LEGACY_STREAM : (chunk.streamIndex ?? keys[0]);
      // A chunk tagged for a mic nobody declared would land on a key that
      // neither the cadence nor `finalise` iterates, so its audio would be
      // invisible — excluded from the byte counters and never uploaded — until
      // its buffer alone crossed the bound and stopped the whole recording.
      // It goes to the first declared stream instead: attributing a chunk to
      // the wrong mic is recoverable, and losing it silently is not.
      if (!legacy && !keys.includes(key)) key = keys[0];
      machineryFor(key).buffer.push(chunk.blob);
    }
    consumed.current = arr.length;
    for (const [key, state] of machinery.current) {
      patch(key, {
        pendingBytes: state.buffer.reduce((total, blob) => total + blob.size, 0),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunksRef, chunkCount, keys, machineryFor, patch]);

  const flushStream = useCallback(
    async (key: number, { final }: { final: boolean }) => {
      const state = machineryFor(key);
      // `halted` stops the cadence, never the close. The bound means "stop
      // recording", not "discard what is already held" — and AC-3 rules out
      // discarding, so a halted stream must still be allowed to finalise.
      if (state.halted && !final) return;
      if (state.busy) {
        if (!final) return;
        // AC-4: wait for the append already in flight rather than skipping the
        // close. Returning here would leave the resumable session open with
        // the bytes we had already PUT stranded and unrecoverable.
        await state.inflight;
      }
      // Per-stream backoff, honoured against a shared cadence rather than by
      // re-arming a timer — see the effect below for why that has to be one
      // interval and not one timer per attempt.
      if (!final && Date.now() < state.nextAttemptAt) return;

      const active = await openSession(key);
      if (!active || !state.upload) {
        patch(key, { status: 'delayed' });
        return;
      }

      const held = new Blob(state.buffer);
      // Non-final chunks must be a whole number of 256 KiB units; the
      // remainder waits. GCS rejects a misaligned intermediate PUT outright,
      // and the upload cannot continue afterwards.
      const length = final ? held.size : alignedLength(held.size);
      if (length === 0 && !final) {
        setPerStream((prev) => {
          const current = prev[key]?.status;
          // A stream already degraded or stopped is not promoted back to
          // "uploading" by a flush that had nothing aligned to send.
          if (
            current === 'degraded' ||
            current === 'stopped' ||
            current === 'uploading'
          ) {
            return prev;
          }
          return {
            ...prev,
            [key]: { ...(prev[key] ?? blankStream(key)), status: 'uploading' },
          };
        });
        return;
      }

      state.busy = true;
      const inflight = state.upload.send(held.slice(0, length), { final });
      state.inflight = inflight.then(
        () => undefined,
        () => undefined,
      );
      try {
        const outcome = await inflight;
        if (outcome.ok) {
          const rest = held.slice(length);
          state.buffer = rest.size ? [rest] : [];
          state.attempt = 0;
          state.nextAttemptAt = 0;
          patch(key, {
            pendingBytes: rest.size,
            uploadedBytes: outcome.committed,
            status: final ? 'idle' : 'uploading',
          });
          setMessage(null);
          return;
        }

        if (!outcome.retryable) {
          patch(key, { status: 'delayed' });
          setMessage(state.session?.degraded_message ?? null);
          return;
        }

        state.attempt += 1;
        state.nextAttemptAt = Date.now() + backoffMs(state.attempt);
        // AC-2: "a transient 'Saving delayed' indicator, not an error". The
        // audio is not lost — it is held, and the next attempt sends it.
        patch(key, { status: state.attempt > 2 ? 'degraded' : 'delayed' });
        if (state.attempt > 2) {
          // AC-3: the message comes from the breaker config the server
          // serves, never a string typed into this component.
          setMessage(state.session?.degraded_message ?? null);
        }
      } finally {
        state.busy = false;
      }
    },
    [openSession, machineryFor, patch],
  );

  // Absorb whatever the recorder has produced, and enforce the bound per mic.
  useEffect(() => {
    absorb();
    let tripped = false;
    for (const [, state] of machinery.current) {
      if (state.halted) continue;
      const held = state.buffer.reduce((total, blob) => total + blob.size, 0);
      if (held >= LOCAL_BOUND_BYTES) {
        tripped = true;
        break;
      }
    }
    if (!tripped) return;

    // AC-3: "when the local bound is reached, recording stops gracefully with
    // an explicit message rather than silently discarding audio". Every
    // buffer is kept — dropping one is the behaviour the criterion rules out.
    //
    // One mic tripping halts them all, because the meeting is the unit: a
    // transcript missing one participant from the ten-minute mark is not the
    // legal record O-06 assembles, and letting the others run would hide that.
    for (const [key, state] of machinery.current) {
      state.halted = true;
      patch(key, { status: 'stopped' });
    }
    setMessage(BOUND_REACHED_MESSAGE);
    onBoundReached?.();
  }, [absorb, onBoundReached, patch]);

  /**
   * Flush on a fixed cadence while recording.
   *
   * One interval, and deliberately nothing byte-related in the dependency
   * array. A `setTimeout` re-armed whenever `pendingBytes` changed could never
   * elapse: `MediaRecorder` is started with a 20 ms timeslice, so chunks — and
   * therefore pending bytes — arrive about fifty times a second per mic, which
   * is far more often than the 30 s cadence. The effect tore the timer down and
   * re-armed it at full delay each time, so no incremental append ever ran and
   * the entire meeting stayed in memory until the stop button. A tab crash at
   * minute nine lost everything, which is the failure the resumable session
   * exists to prevent.
   *
   * Per-stream backoff lives on the machinery (`nextAttemptAt`) instead, so one
   * stream waiting out a retry cannot delay a healthy one (AC-3).
   */
  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(() => {
      for (const key of keysRef.current) {
        void flushStream(key, { final: false });
      }
    }, ALIGN_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [recording, flushStream]);

  const finalise = useCallback(async () => {
    absorb();
    // allSettled, not all: AC-4 finalises every stream. One mic whose session
    // is unreachable must not stop the others from closing their objects.
    await Promise.allSettled(
      keys.map((key) => flushStream(key, { final: true })),
    );
  }, [absorb, flushStream, keys]);

  const aggregate = useMemo(() => {
    const entries = keys.map((key) => perStream[key] ?? blankStream(key));
    const status = entries.reduce<UploadStatus>(
      (worst, entry) =>
        STATUS_RANK[entry.status] > STATUS_RANK[worst] ? entry.status : worst,
      'idle',
    );
    return {
      status,
      uploadedBytes: entries.reduce((total, e) => total + e.uploadedBytes, 0),
      pendingBytes: entries.reduce((total, e) => total + e.pendingBytes, 0),
      streams: entries,
    };
  }, [keys, perStream]);

  return {
    status: aggregate.status,
    uploadedBytes: aggregate.uploadedBytes,
    pendingBytes: aggregate.pendingBytes,
    message,
    streams: aggregate.streams,
    finalise,
  };
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
