'use client';

/**
 * RecorderControl — start and stop the meeting recording (F-02, §11).
 *
 * §11 describes this as "consent modal → getUserMedia → WebSocket streaming
 * with parallel GCS spool. Persistent recording indicator, elapsed timer, and
 * a reconnect state". F-02 delivers the first two and the indicator; the
 * streaming and the spool are F-04's and F-03's, and this component does not
 * know they exist — the hook it uses has no socket in it.
 *
 * Consent is checked before this renders as usable at all (F-01, IG-08): the
 * microphone cannot open without an active ConsentRecord, and that is enforced
 * server-side too.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CloudOff, Mic, Square, UploadCloud } from 'lucide-react';

import {
  useMeetingRecorder,
  SAMPLE_RATE,
  type UseMeetingRecorder,
} from '@/hooks/useMeetingRecorder';
import {
  useMultiMicRecorder,
  type StreamDevice,
  type UseMultiMicRecorder,
} from '@/hooks/useMultiMicRecorder';
import {
  useChunkUploader,
  type UseChunkUploader,
} from '@/hooks/useChunkUploader';
import { finaliseRecording, openRecording } from '@/lib/onboarding-sessions';
import type { MicAssignment } from '@/hooks/useAudioDevices';

export interface RecorderControlProps {
  /** F-01: false keeps the control inert and pointing at the consent modal. */
  consentGranted: boolean;
  onRecordConsent?: () => void;
  /** F-03: which session the recording attaches to. */
  sessionId?: string | null;
  /** F-04: forward binary audio to the live WebSocket for STT. */
  sendBinary?: (data: ArrayBuffer | Uint8Array) => void;
  /** F-04: send start/stop control frames to the live WebSocket. */
  sendControl?: (frame: Record<string, unknown>) => void;
  /** O-01: mic assignments from MicSetup. When present, multi-mic recording is used. */
  micAssignments?: MicAssignment[];
  /** Injected in tests; the hook is the default. */
  recorder?: UseMeetingRecorder;
  /** Injected in tests; the hook is the default. */
  uploader?: UseChunkUploader;
}

/** mm:ss. Hours are not shown: a meeting that long has other problems. */
export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  const remainder = whole % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
}

export default function RecorderControl({
  consentGranted,
  onRecordConsent,
  sessionId,
  sendBinary,
  sendControl,
  micAssignments = [],
  recorder,
  uploader: injectedUploader,
}: RecorderControlProps) {
  const multiDevices: StreamDevice[] = useMemo(
    () =>
      micAssignments.map((a) => ({
        deviceId: a.deviceId,
        streamIndex: a.streamIndex,
        label: a.label,
      })),
    [micAssignments],
  );
  const useMulti = micAssignments.length > 0;

  const singleMic = useMeetingRecorder();
  const multiMic = useMultiMicRecorder(multiDevices);
  const live: UseMeetingRecorder | UseMultiMicRecorder = recorder ?? (useMulti ? multiMic : singleMic);

  const { state, error, elapsedSeconds, chunksRef, chunkCount, start, stop } = live;
  const recording = state === 'recording';
  const busy = state === 'requesting' || state === 'stopping';

  const [recordingId, setRecordingId] = useState<string | null>(null);
  const elapsedAtStop = useRef(0);
  const sentChunkIndex = useRef(0);
  /** Set below, so the bound handler can reach `end` without a cycle. */
  const endRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    if (!recording || !sendBinary) return;
    const chunks = chunksRef.current;
    while (sentChunkIndex.current < chunks.length) {
      const chunk = chunks[sentChunkIndex.current];
      const streamIdx = 'streamIndex' in chunk ? (chunk as { streamIndex: number }).streamIndex : -1;
      // O-09: only the mic the energy gate had open reaches STT. Separate mics
      // in one room hear each other, and transcribing every copy makes the
      // record say two people said the same sentence.
      //
      // The uploader deliberately does not consult this — every chunk still
      // reaches its own GCS object, because a legal archive with holes in it is
      // worse than one containing bleed.
      const gated = 'gateOpen' in chunk && (chunk as { gateOpen: boolean }).gateOpen === false;
      if (gated) {
        sentChunkIndex.current += 1;
        continue;
      }
      chunk.blob.arrayBuffer().then((buf) => {
        if (streamIdx >= 0) {
          const audio = new Uint8Array(buf);
          const prefixed = new Uint8Array(1 + audio.length);
          prefixed[0] = streamIdx;
          prefixed.set(audio, 1);
          sendBinary(prefixed);
        } else {
          sendBinary(new Uint8Array(buf));
        }
      });
      sentChunkIndex.current += 1;
    }
  }, [recording, chunkCount, sendBinary, chunksRef]);

  // AC-6. Named from the mic assignments rather than shown as an index: the
  // operator assigned "Sarah Kelso" to a mic, not "stream 1".
  const activeIndex =
    'activeStreamIndex' in live ? (live as UseMultiMicRecorder).activeStreamIndex : null;
  const activeSpeaker =
    activeIndex === null
      ? null
      : (micAssignments.find((a) => a.streamIndex === activeIndex)?.label ??
        `Mic ${activeIndex}`);

  const ownUploader = useChunkUploader({
    recordingId,
    chunksRef,
    chunkCount,
    recording,
    // O-07: one upload session per mic. Omitted when there are no
    // assignments, which keeps the single-mic upload exactly as it was.
    streams: useMulti ? multiDevices : undefined,
    // AC-3: the local bound stops the recording rather than discarding audio.
    //
    // `endRef`, not `stop`: stopping the recorder alone left the held audio
    // unflushed and the recording row in RECORDING with no BrandAsset, while
    // the operator was told ten minutes were "waiting to upload". Going through
    // the same path as the stop button is what makes that message true. A ref
    // because `end` is declared below and closes over this uploader.
    onBoundReached: () => void endRef.current?.(),
  });
  const uploader = injectedUploader ?? ownUploader;

  const begin = useCallback(async () => {
    sentChunkIndex.current = 0;
    let rid: string | null = null;
    try {
      const opened = await openRecording(String(sessionId));
      rid = opened.recording_id;
      setRecordingId(rid);
    } catch {
      setRecordingId(null);
    }
    await start();
    if (sendControl && rid) {
      const frame: Record<string, unknown> = {
        type: 'start',
        recording_id: rid,
        codec: 'audio/webm;codecs=opus',
        sample_rate: SAMPLE_RATE,
      };
      if (micAssignments.length > 0) {
        frame.streams = micAssignments.map((a) => ({
          stream_index: a.streamIndex,
          speaker_name: a.label,
          speaker_role: a.role,
        }));
      }
      sendControl(frame);
    }
  }, [sessionId, start, sendControl, micAssignments]);

  const end = useCallback(async () => {
    elapsedAtStop.current = elapsedSeconds;
    if (sendControl) {
      sendControl({ type: 'stop' });
    }
    await stop();
    await uploader.finalise();
    if (recordingId) {
      try {
        await finaliseRecording(recordingId, elapsedAtStop.current);
      } catch {
        // Retried by the operator pressing stop again, and idempotent when
        // they do. Throwing here would leave the UI stuck mid-stop.
      }
    }
  }, [elapsedSeconds, stop, uploader, recordingId, sendControl]);

  // In an effect, not during render: the bound handler only fires from a
  // timer, so it never needs a value newer than the last commit.
  useEffect(() => {
    endRef.current = end;
  }, [end]);

  if (!consentGranted) {
    return (
      <div className="space-y-2">
        {/*
          F-01 AC-1: visible, inert, reason stated inline, and clicking it
          opens the consent modal. aria-disabled rather than disabled, because
          a disabled button cannot be clicked and the criterion requires that
          it can.
        */}
        <button
          type="button"
          aria-disabled="true"
          onClick={onRecordConsent}
          className="flex w-full items-center gap-2 rounded border border-brand-electric/40 px-3 py-2 text-sm text-white"
        >
          <Mic aria-hidden="true" className="h-4 w-4 shrink-0" />
          Start recording
        </button>
        <p className="text-xs text-amber-300">Record consent to enable recording</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={recording ? end : begin}
        disabled={busy}
        className={`flex w-full items-center gap-2 rounded border px-3 py-2 text-sm disabled:opacity-60 ${
          recording
            ? 'border-rose-400/50 bg-rose-500/15 text-white'
            : 'border-white/15 text-white'
        }`}
      >
        {recording ? (
          <Square aria-hidden="true" className="h-4 w-4 shrink-0" />
        ) : (
          <Mic aria-hidden="true" className="h-4 w-4 shrink-0" />
        )}
        {recording ? 'Stop recording' : busy ? 'Starting…' : 'Start recording'}
      </button>

      {recording && (
        /*
          AC-3: "an unmistakable recording indicator with a running elapsed
          timer". role=status rather than alert — it is a persistent state, and
          an alert would re-announce itself to a screen reader every second.
        */
        <div
          role="status"
          className="flex items-center gap-2 rounded border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-100"
        >
          <span
            aria-hidden="true"
            className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-rose-400"
          />
          <span className="font-medium">Recording</span>
          {/*
            AC-6: which mic is feeding STT right now. Without it an operator
            cannot tell a working gate from a mic that stopped being picked up,
            and both look like a transcript missing somebody's words.
          */}
          {activeSpeaker && (
            <span
              className="rounded bg-rose-400/20 px-1.5 py-0.5 text-xs"
              data-testid="active-speaker"
            >
              {activeSpeaker}
            </span>
          )}
          {/* tabular-nums so the row does not jitter as digits change. */}
          <span className="ml-auto tabular-nums" data-testid="elapsed">
            {formatElapsed(elapsedSeconds)}
          </span>
        </div>
      )}

      {/*
        AC-2: "the operator sees a transient 'Saving delayed' indicator, not an
        error". Distinct from the degraded state below, which is the breaker's
        message and means uploads have been failing for a while.
      */}
      {uploader.status === 'delayed' && (
        <p role="status" className="flex items-center gap-2 text-xs text-brand-silver">
          <UploadCloud aria-hidden="true" className="h-3 w-3 shrink-0" />
          Saving delayed
        </p>
      )}

      {(uploader.status === 'degraded' || uploader.status === 'stopped') &&
        uploader.message && (
          <p
            role="alert"
            className="flex items-start gap-2 text-xs text-amber-300"
          >
            <CloudOff aria-hidden="true" className="mt-0.5 h-3 w-3 shrink-0" />
            {uploader.message}
          </p>
        )}

      {error && (
        <p role="alert" className="text-xs text-amber-300">
          {error}
        </p>
      )}
    </div>
  );
}
