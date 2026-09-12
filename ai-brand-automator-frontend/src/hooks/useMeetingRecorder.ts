'use client';

/**
 * Microphone capture for the meeting view (F-02, Design §4.3, §11).
 *
 * Knows nothing about sockets, uploads or Django. The card is firm about that:
 * "Keep the recorder in a hook with no knowledge of the socket. F-03 and F-04
 * both consume its output queue, and the seam is what makes F-06's record-only
 * mode possible without a rewrite." So this produces chunks and state, and
 * somebody else decides where they go.
 *
 * Deliberately **not** built on `useVoiceInput`. That hook is hold-to-talk
 * dictation for the chat box: it posts a whole blob to Django and falls back
 * across `audio/webm` → `webm;codecs=opus` → `ogg;codecs=opus`, taking whatever
 * the browser offers. AC-2 rules that out — "recording is refused with a named,
 * testable error rather than silently falling back to a codec the adapter
 * cannot read". Sharing the hook would import the exact behaviour the criterion
 * forbids.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderState =
  | 'idle'
  | 'requesting'
  | 'recording'
  | 'stopping'
  | 'blocked'
  | 'unsupported';

/**
 * Opus, in whichever container the browser packages it in.
 *
 * Chromium produces WebM, Firefox produces Ogg; both carry an opus stream,
 * which is what §4.3's STT adapter reads. Choosing between *containers* is not
 * the fallback AC-2 forbids — that is falling back to a different **codec**,
 * which is why nothing without `codecs=opus` appears here and why the list
 * ending is a refusal rather than a default.
 */
export const OPUS_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/ogg;codecs=opus',
] as const;

/**
 * §4.3's expectation, and F-03's dependency.
 *
 * The MediaRecorder default fires `ondataavailable` once, at stop — a
 * forty-five minute meeting would arrive as a single blob with nothing to
 * stream. The technical note is explicit that F-03's chunking depends on a
 * predictable cadence.
 */
export const TIMESLICE_MS = 20;

export const SAMPLE_RATE = 48000;

export const UNSUPPORTED_MESSAGE =
  'This browser cannot record opus audio, which the transcription service ' +
  'requires. Try Chrome, Edge or Firefox.';

export const BLOCKED_MESSAGE =
  "Microphone blocked. Enable it in your browser's site settings and press " +
  'record again';

export interface RecordedChunk {
  blob: Blob;
  /** Position in the queue. F-03 drains in this order and must not reorder. */
  index: number;
}

export interface UseMeetingRecorder {
  state: RecorderState;
  /** Set when state is `blocked` or `unsupported`; null otherwise. */
  error: string | null;
  /** Seconds of audio recorded, from the audio timeline. */
  elapsedSeconds: number;
  /** Stable ref to the chunk array. Read by index; never replaced. */
  chunksRef: React.RefObject<RecordedChunk[]>;
  /** Increments when a new chunk arrives — use as a dependency trigger. */
  chunkCount: number;
  mimeType: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

/** The first opus type this browser will actually produce, or null. */
export function supportedOpusMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  if (typeof MediaRecorder.isTypeSupported !== 'function') return null;
  return OPUS_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function useMeetingRecorder(): UseMeetingRecorder {
  const [state, setState] = useState<RecorderState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsed] = useState(0);
  const chunksRef = useRef<RecordedChunk[]>([]);
  const [chunkCount, setChunkCount] = useState(0);
  const [mimeType, setMimeType] = useState<string | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const startedAt = useRef(0);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);
  const nextIndex = useRef(0);

  /**
   * Elapsed comes from the audio clock, never from Date.now().
   *
   * FR-REC-02: "a stalled tab does not report phantom duration". An
   * AudioContext's currentTime advances with the audio hardware and stalls when
   * the audio does, so a machine that sleeps mid-meeting reports the length of
   * the audio rather than the length of the nap — which is also what B-08
   * established `duration_s` to mean. Wall-clock would disagree with the asset
   * by exactly the sleep.
   */
  const readElapsed = useCallback(() => {
    const context = audioContext.current;
    if (!context) return 0;
    return Math.max(0, context.currentTime - startedAt.current);
  }, []);

  const teardown = useCallback(() => {
    if (ticker.current) {
      clearInterval(ticker.current);
      ticker.current = null;
    }
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    void audioContext.current?.close?.();
    audioContext.current = null;
    recorder.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);

    const type = supportedOpusMimeType();
    if (!type) {
      // Refused, loudly. Recording in a codec §4.3's adapter cannot read would
      // produce a meeting's worth of audio that fails at transcription, an
      // hour after the operator could have done anything about it.
      setState('unsupported');
      setError(UNSUPPORTED_MESSAGE);
      return;
    }

    setState('requesting');
    let granted: MediaStream;
    try {
      granted = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: SAMPLE_RATE, channelCount: 1 },
      });
    } catch {
      // AC-1: an explicit state, and the control back to ready. Not a spinner —
      // a spinner after a denied prompt is a dead end the operator cannot
      // even retry from, and the prompt will not reappear on its own.
      setState('blocked');
      setError(BLOCKED_MESSAGE);
      return;
    }

    stream.current = granted;
    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    audioContext.current = context;

    /*
     * Resume before reading the clock, and before recording starts.
     *
     * A fresh AudioContext is not necessarily running: under an autoplay
     * policy it begins `suspended`, and a suspended context's currentTime does
     * not advance at all — a whole meeting would report a duration near zero.
     * Even when it does start, there is a startup gap before the clock moves.
     *
     * Measured in Chromium: reading currentTime immediately after construction
     * and again after an 800 ms recording gave 0.54 s, a 260 ms shortfall the
     * jsdom tests could not see because their clock is a number the test sets.
     * Over 45 minutes that is inside FR-REC-02's one-second budget by luck
     * rather than by design, and the suspended case is not inside it at all.
     */
    if (context.state === 'suspended') {
      await context.resume();
    }
    startedAt.current = context.currentTime;

    const media = new MediaRecorder(granted, { mimeType: type });
    recorder.current = media;
    setMimeType(type);

    media.ondataavailable = (event: BlobEvent) => {
      if (!event.data || event.data.size === 0) return;
      const index = nextIndex.current;
      nextIndex.current += 1;
      chunksRef.current.push({ blob: event.data, index });
      setChunkCount((n) => n + 1);
    };

    media.start(TIMESLICE_MS);
    setState('recording');
    setElapsed(0);
    ticker.current = setInterval(() => setElapsed(readElapsed()), 200);
  }, [readElapsed]);

  const stop = useCallback(async () => {
    const media = recorder.current;
    if (!media || media.state === 'inactive') {
      setState('idle');
      teardown();
      return;
    }

    setState('stopping');
    // The last partial buffer only arrives on stop; without requestData a
    // recording ends a timeslice short, which is a truncated final word.
    await new Promise<void>((resolve) => {
      media.onstop = () => resolve();
      media.stop();
    });

    // Read before teardown closes the context: currentTime is meaningless
    // afterwards, and this is the value B-08's duration_s comes from.
    setElapsed(readElapsed());
    setState('idle');
    teardown();
  }, [readElapsed, teardown]);

  /**
   * AC-3: "the browser tab title reflects the recording state so a backgrounded
   * tab is still obvious". The one place a recording indicator survives the
   * operator switching away, which is when forgetting is most likely.
   */
  useEffect(() => {
    if (state !== 'recording') return;
    const previous = document.title;
    document.title = `● Recording — ${previous}`;
    return () => {
      document.title = previous;
    };
  }, [state]);

  /**
   * AC-4: a tab close during recording is confirmed, "naming what is at risk".
   *
   * Registered only while recording. A permanently installed handler would
   * warn on every navigation away from a meeting that was never recording,
   * which is how operators learn to click through the dialog without reading.
   *
   * Browsers ignore custom text now, but returnValue is still what triggers
   * the prompt at all.
   */
  useEffect(() => {
    if (state !== 'recording') return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue =
        'Recording is still running. Closing this tab loses the audio ' +
        'captured so far.';
      return event.returnValue;
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [state]);

  useEffect(() => teardown, [teardown]);

  return { state, error, elapsedSeconds, chunksRef, chunkCount, mimeType, start, stop };
}
