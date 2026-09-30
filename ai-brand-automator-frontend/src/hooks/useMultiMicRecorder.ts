'use client';

/**
 * Multi-mic recording for speaker-attributed transcripts (O-02).
 *
 * Opens one MediaRecorder per assigned mic. Each produces its own chunk
 * stream tagged with a streamIndex so downstream consumers (F-04 WebSocket,
 * F-03 GCS uploader, O-03 multi-stream protocol) know which speaker
 * produced each chunk.
 *
 * A single AudioContext drives the elapsed timer across all streams —
 * AC-3 requires the timer to be accurate regardless of how many mics
 * are active.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  TIMESLICE_MS,
  SAMPLE_RATE,
  UNSUPPORTED_MESSAGE,
  BLOCKED_MESSAGE,
  supportedOpusMimeType,
  type RecorderState,
} from '@/hooks/useMeetingRecorder';
import { EnergyGate, rmsOf } from '@/lib/energy-gate';

/**
 * How often the gate re-reads per-channel energy.
 *
 * The card specifies a ~100 ms window, which is also short enough that the
 * ~300 ms hold is evaluated a few times before it can expire.
 */
export const GATE_INTERVAL_MS = 100;

export { SAMPLE_RATE, TIMESLICE_MS };

export interface StreamDevice {
  deviceId: string;
  streamIndex: number;
  label: string;
}

export interface TaggedChunk {
  blob: Blob;
  index: number;
  streamIndex: number;
  /**
   * Whether the energy gate had this mic open when the chunk was produced
   * (O-09).
   *
   * Recorded at production rather than checked at send time: chunks arrive
   * every 20 ms and the open channel changes between them, so asking "is this
   * mic open now?" would mis-gate the audio either side of a handover.
   *
   * Only the WebSocket honours it. The GCS uploader ignores it entirely — the
   * per-mic archive O-07 builds stays complete, because a legal record with
   * holes in it is worse than one containing bleed.
   */
  gateOpen: boolean;
}

export interface UseMultiMicRecorder {
  state: RecorderState;
  error: string | null;
  elapsedSeconds: number;
  chunksRef: React.RefObject<TaggedChunk[]>;
  chunkCount: number;
  mimeType: string | null;
  /** The mic currently feeding STT, for AC-6's indicator. */
  activeStreamIndex: number | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

interface StreamHandle {
  streamIndex: number;
  mediaStream: MediaStream;
  recorder: MediaRecorder;
  analyser: AnalyserNode | null;
  // Pinned to ArrayBuffer, not ArrayBufferLike: getByteTimeDomainData cannot
  // write into a SharedArrayBuffer-backed view.
  samples: Uint8Array<ArrayBuffer> | null;
}

export function useMultiMicRecorder(
  devices: StreamDevice[],
): UseMultiMicRecorder {
  const [state, setState] = useState<RecorderState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsed] = useState(0);
  const chunksRef = useRef<TaggedChunk[]>([]);
  const [chunkCount, setChunkCount] = useState(0);
  const [mimeType, setMimeType] = useState<string | null>(null);

  const [activeStreamIndex, setActiveStreamIndex] = useState<number | null>(null);

  const handles = useRef<StreamHandle[]>([]);
  const audioContext = useRef<AudioContext | null>(null);
  const startedAt = useRef(0);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);
  const nextIndex = useRef(0);
  const gate = useRef(new EnergyGate());
  const gateTicker = useRef<ReturnType<typeof setInterval> | null>(null);
  /**
   * The open channel, read synchronously when tagging a chunk.
   *
   * Chunks arrive every 20 ms — far more often than React commits — so the
   * recorder callback cannot read the state value and see the current decision.
   */
  const openChannel = useRef<number | null>(null);

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
    if (gateTicker.current) {
      clearInterval(gateTicker.current);
      gateTicker.current = null;
    }
    openChannel.current = null;
    setActiveStreamIndex(null);
    for (const h of handles.current) {
      if (h.recorder.state !== 'inactive') {
        try { h.recorder.stop(); } catch { /* already stopped */ }
      }
      h.mediaStream.getTracks().forEach((t) => t.stop());
    }
    handles.current = [];
    void audioContext.current?.close?.();
    audioContext.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);

    const type = supportedOpusMimeType();
    if (!type) {
      setState('unsupported');
      setError(UNSUPPORTED_MESSAGE);
      return;
    }

    if (devices.length === 0) {
      setState('unsupported');
      setError('No microphones assigned. Set up microphones first.');
      return;
    }

    setState('requesting');

    const opened: StreamHandle[] = [];
    for (const dev of devices) {
      let mediaStream: MediaStream;
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: { deviceId: { exact: dev.deviceId }, sampleRate: SAMPLE_RATE, channelCount: 1 },
        });
      } catch {
        for (const h of opened) {
          h.mediaStream.getTracks().forEach((t) => t.stop());
        }
        setState('blocked');
        setError(BLOCKED_MESSAGE);
        return;
      }

      const recorder = new MediaRecorder(mediaStream, { mimeType: type });
      const streamIndex = dev.streamIndex;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (!event.data || event.data.size === 0) return;
        const index = nextIndex.current;
        nextIndex.current += 1;
        chunksRef.current.push({
          blob: event.data,
          index,
          streamIndex,
          // A single-mic recording has one stream and no gate decision yet;
          // treat it as open so the pre-O-09 path is unchanged.
          gateOpen:
            openChannel.current === null || openChannel.current === streamIndex,
        });
        setChunkCount((n) => n + 1);
      };

      opened.push({ streamIndex, mediaStream, recorder, analyser: null, samples: null });
    }

    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    if (context.state === 'suspended') {
      await context.resume();
    }
    audioContext.current = context;
    startedAt.current = context.currentTime;

    // O-09: one analyser per mic, so the gate can compare their energy.
    // Wrapped because a jsdom AudioContext has no createAnalyser — the gate
    // then never opens, `gateOpen` stays true for every chunk, and behaviour
    // falls back to O-02's send-everything model rather than failing.
    for (const h of opened) {
      try {
        const analyser = context.createAnalyser();
        analyser.fftSize = 2048;
        context.createMediaStreamSource(h.mediaStream).connect(analyser);
        h.analyser = analyser;
        h.samples = new Uint8Array(new ArrayBuffer(analyser.fftSize));
      } catch {
        h.analyser = null;
      }
    }

    handles.current = opened;
    setMimeType(type);

    if (opened.length > 1 && opened.some((h) => h.analyser !== null)) {
      gate.current = new EnergyGate();
      gateTicker.current = setInterval(() => {
        const rms = new Map<number, number>();
        for (const h of handles.current) {
          if (!h.analyser || !h.samples) continue;
          h.analyser.getByteTimeDomainData(h.samples);
          rms.set(h.streamIndex, rmsOf(h.samples));
        }
        if (rms.size === 0) return;
        const decision = gate.current.decide(rms, Date.now());
        openChannel.current = decision.active;
        if (decision.changed) setActiveStreamIndex(decision.active);
      }, GATE_INTERVAL_MS);
    }

    for (const h of opened) {
      h.recorder.start(TIMESLICE_MS);
    }

    setState('recording');
    setElapsed(0);
    ticker.current = setInterval(() => setElapsed(readElapsed()), 200);
  }, [devices, readElapsed]);

  const stop = useCallback(async () => {
    const active = handles.current.filter((h) => h.recorder.state !== 'inactive');
    if (active.length === 0) {
      setState('idle');
      teardown();
      return;
    }

    setState('stopping');

    await Promise.all(
      active.map(
        (h) =>
          new Promise<void>((resolve) => {
            h.recorder.onstop = () => resolve();
            h.recorder.stop();
          }),
      ),
    );

    setElapsed(readElapsed());
    setState('idle');
    teardown();
  }, [readElapsed, teardown]);

  useEffect(() => {
    if (state !== 'recording') return;
    const previous = document.title;
    document.title = `● Recording — ${previous}`;
    return () => {
      document.title = previous;
    };
  }, [state]);

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

  return {
    state,
    error,
    elapsedSeconds,
    chunksRef,
    chunkCount,
    mimeType,
    activeStreamIndex,
    start,
    stop,
  };
}
