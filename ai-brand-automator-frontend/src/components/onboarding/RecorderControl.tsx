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

import { Mic, Square } from 'lucide-react';

import {
  useMeetingRecorder,
  type UseMeetingRecorder,
} from '@/hooks/useMeetingRecorder';

export interface RecorderControlProps {
  /** F-01: false keeps the control inert and pointing at the consent modal. */
  consentGranted: boolean;
  onRecordConsent?: () => void;
  /** Injected in tests; the hook is the default. */
  recorder?: UseMeetingRecorder;
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
  recorder,
}: RecorderControlProps) {
  /*
   * The hook is always called and the injection only chooses which result to
   * use. `recorder ?? useMeetingRecorder()` would read more directly and is a
   * rules-of-hooks violation that happens to be safe today — the kind that
   * stops being safe the moment someone makes the prop conditional. An
   * eslint-disable on that rule is not worth the two lines it saves.
   *
   * Injection rather than a context provider: a context to hand one hook to
   * one component is more machinery than this seam needs, and F-03 and F-04
   * will consume the hook directly rather than through this component.
   */
  const own = useMeetingRecorder();
  const live = recorder ?? own;

  const { state, error, elapsedSeconds, start, stop } = live;
  const recording = state === 'recording';
  const busy = state === 'requesting' || state === 'stopping';

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
        onClick={recording ? stop : start}
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
          {/* tabular-nums so the row does not jitter as digits change. */}
          <span className="ml-auto tabular-nums" data-testid="elapsed">
            {formatElapsed(elapsedSeconds)}
          </span>
        </div>
      )}

      {error && (
        <p role="alert" className="text-xs text-amber-300">
          {error}
        </p>
      )}
    </div>
  );
}
