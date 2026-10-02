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
}

export interface UseMultiMicRecorder {
  state: RecorderState;
  error: string | null;
  elapsedSeconds: number;
  /**
   * Per-mic chunks, one WebM stream per microphone. O-07's GCS archive reads
   * these, so they are never gated — a legal record with holes in it is worse
   * than one containing bleed.
   */
  chunksRef: React.RefObject<TaggedChunk[]>;
  chunkCount: number;
  /**
   * The gated stream: one WebM container carrying only whoever the gate had
   * open, with `streamIndex` naming them (O-09). This is what goes to STT.
   *
   * It exists because gating cannot be done by dropping encoded chunks.
   * Splicing two MediaRecorder outputs into one byte stream produces a
   * malformed container: measured with ffmpeg, a strict parser recovers only
   * the audio before the first handover and silently discards the rest, while
   * a lenient one collapses every later timestamp onto the splice point —
   * which would destroy the `t_start` attribution and provenance rely on.
   *
   * So the gate runs *before* the encoder, as gain on each mic's node, and one
   * recorder captures the result.
   */
  gatedChunksRef: React.RefObject<TaggedChunk[]>;
  gatedChunkCount: number;
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
  /** Gain the gate drives: 1 when this mic is open, 0 when it is suppressed. */
  gain: GainNode | null;
}

export function useMultiMicRecorder(
  devices: StreamDevice[],
): UseMultiMicRecorder {
  const [state, setState] = useState<RecorderState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsed] = useState(0);
  const chunksRef = useRef<TaggedChunk[]>([]);
  const [chunkCount, setChunkCount] = useState(0);
  const gatedChunksRef = useRef<TaggedChunk[]>([]);
  const [gatedChunkCount, setGatedChunkCount] = useState(0);
  const [mimeType, setMimeType] = useState<string | null>(null);

  const [activeStreamIndex, setActiveStreamIndex] = useState<number | null>(null);

  const handles = useRef<StreamHandle[]>([]);
  const audioContext = useRef<AudioContext | null>(null);
  const startedAt = useRef(0);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);
  const nextIndex = useRef(0);
  const nextGatedIndex = useRef(0);
  const gatedRecorderRef = useRef<MediaRecorder | null>(null);
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
    const gated = gatedRecorderRef.current;
    if (gated && gated.state !== 'inactive') {
      try {
        gated.stop();
      } catch {
        /* already stopped */
      }
    }
    gatedRecorderRef.current = null;
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
        chunksRef.current.push({ blob: event.data, index, streamIndex });
        setChunkCount((n) => n + 1);
      };

      opened.push({
        streamIndex,
        mediaStream,
        recorder,
        analyser: null,
        samples: null,
        gain: null,
      });
    }

    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    if (context.state === 'suspended') {
      await context.resume();
    }
    audioContext.current = context;
    startedAt.current = context.currentTime;

    // O-09: the gated graph. Each mic gets an analyser (to measure energy) and
    // a gain node (for the gate to open or shut it), and all the gains feed one
    // destination that a single recorder captures.
    //
    // The gate has to act here, on the signal, rather than on encoded chunks.
    // Splicing two MediaRecorder outputs into one byte stream makes a malformed
    // container — measured with ffmpeg, a strict parser recovers only the audio
    // before the first handover and discards the rest, and a lenient one
    // collapses every later timestamp onto the splice point.
    //
    // Wrapped because jsdom's AudioContext has none of these methods. The gate
    // then never arms, `gatedChunksRef` stays empty, and callers fall back to
    // the per-mic chunks — O-02's behaviour — rather than failing.
    let gatedRecorder: MediaRecorder | null = null;
    try {
      const merged = context.createMediaStreamDestination();
      for (const h of opened) {
        const source = context.createMediaStreamSource(h.mediaStream);
        const analyser = context.createAnalyser();
        analyser.fftSize = 2048;
        source.connect(analyser);
        h.analyser = analyser;
        h.samples = new Uint8Array(new ArrayBuffer(analyser.fftSize));

        const gain = context.createGain();
        // Shut until the gate opens one, so a meeting never starts by sending
        // every mic at once.
        gain.gain.value = 0;
        source.connect(gain);
        gain.connect(merged);
        h.gain = gain;
      }
      if (opened.length > 1) {
        gatedRecorder = new MediaRecorder(merged.stream, { mimeType: type });
        gatedRecorder.ondataavailable = (event: BlobEvent) => {
          if (!event.data || event.data.size === 0) return;
          const index = nextGatedIndex.current;
          nextGatedIndex.current += 1;
          // The open channel at the moment this slice was encoded — which is
          // what tells the server who was speaking.
          gatedChunksRef.current.push({
            blob: event.data,
            index,
            streamIndex: openChannel.current ?? opened[0].streamIndex,
          });
          setGatedChunkCount((n) => n + 1);
        };
      }
    } catch {
      gatedRecorder = null;
      for (const h of opened) {
        h.analyser = null;
        h.gain = null;
      }
    }

    handles.current = opened;
    gatedRecorderRef.current = gatedRecorder;
    setMimeType(type);

    if (gatedRecorder !== null) {
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
        // Gain, not chunk filtering: the suppressed mics contribute silence to
        // the merged signal, so the encoder sees one continuous stream.
        for (const h of handles.current) {
          if (h.gain) h.gain.gain.value = h.streamIndex === decision.active ? 1 : 0;
        }
        if (decision.changed) setActiveStreamIndex(decision.active);
      }, GATE_INTERVAL_MS);
    }

    for (const h of opened) {
      h.recorder.start(TIMESLICE_MS);
    }
    gatedRecorder?.start(TIMESLICE_MS);

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
    gatedChunksRef,
    gatedChunkCount,
    mimeType,
    activeStreamIndex,
    start,
    stop,
  };
}
