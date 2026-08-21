'use client';

/**
 * Short video snippet recorder (H-02, Design SS11).
 *
 * Captures up to SNIPPET_MAX_SECONDS of video-only footage. Audio is
 * deliberately excluded (AC-3): the meeting's audio recording must continue
 * without interruption, and a second audio track captured under different
 * consent scope is a compliance problem.
 *
 * Parallel to useMeetingRecorder in structure, but simpler: no AudioContext
 * clock (a 30s bound does not need sub-second precision), no chunk streaming,
 * and no codec refusal -- video codec differences across browsers are
 * tolerable because the downstream consumer is frame extraction (H-04), not
 * a real-time transcription adapter.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type SnippetState =
  | 'idle'
  | 'requesting'
  | 'recording'
  | 'stopped'
  | 'unsupported';

export const SNIPPET_MAX_SECONDS = 30;
export const SNIPPET_COUNTDOWN_FROM = 10;

export const VIDEO_MIME_TYPES = [
  'video/webm;codecs=vp8',
  'video/webm',
  'video/mp4',
] as const;

export const UNSUPPORTED_MESSAGE =
  'This browser cannot record video in a supported format. ' +
  'Try Chrome or Edge.';

export const BLOCKED_MESSAGE =
  "Camera blocked. Enable it in your browser's site settings and try again.";

export interface UseSnippetRecorder {
  state: SnippetState;
  error: string | null;
  elapsedSeconds: number;
  secondsRemaining: number | null;
  videoBlob: Blob | null;
  stream: MediaStream | null;
  start: () => Promise<boolean>;
  stop: () => void;
  reset: () => void;
}

export function supportedVideoMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  if (typeof MediaRecorder.isTypeSupported !== 'function') return null;
  return VIDEO_MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? null;
}

export interface SnippetRecorderOptions {
  onStopped?: (blob: Blob) => void;
}

export function useSnippetRecorder(options?: SnippetRecorderOptions): UseSnippetRecorder {
  const [state, setState] = useState<SnippetState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsed] = useState(0);
  const [secondsRemaining, setRemaining] = useState<number | null>(null);
  const [videoBlob, setVideoBlob] = useState<Blob | null>(null);
  const [streamState, setStreamState] = useState<MediaStream | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoStop = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTime = useRef(0);
  const mimeRef = useRef<string | null>(null);
  const onStoppedRef = useRef(options?.onStopped);
  useEffect(() => {
    onStoppedRef.current = options?.onStopped;
  });

  const teardown = useCallback(() => {
    if (ticker.current) {
      clearInterval(ticker.current);
      ticker.current = null;
    }
    if (autoStop.current) {
      clearTimeout(autoStop.current);
      autoStop.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStreamState(null);
    recorder.current = null;
  }, []);

  const stop = useCallback(() => {
    const media = recorder.current;
    if (!media || media.state === 'inactive') {
      teardown();
      return;
    }
    media.stop();
  }, [teardown]);

  const stoppedGuard = useRef(false);

  const start = useCallback(async (): Promise<boolean> => {
    setError(null);
    setVideoBlob(null);
    chunks.current = [];
    stoppedGuard.current = false;

    const type = supportedVideoMimeType();
    if (!type) {
      setState('unsupported');
      setError(UNSUPPORTED_MESSAGE);
      return false;
    }
    mimeRef.current = type;

    setState('requesting');
    let granted: MediaStream;
    try {
      granted = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
    } catch {
      setState('idle');
      setError(BLOCKED_MESSAGE);
      return false;
    }

    streamRef.current = granted;
    setStreamState(granted);

    let media: MediaRecorder;
    try {
      media = new MediaRecorder(granted, { mimeType: type });
    } catch {
      teardown();
      setState('idle');
      setError(UNSUPPORTED_MESSAGE);
      return false;
    }
    recorder.current = media;

    media.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        chunks.current.push(event.data);
      }
    };

    media.onstop = () => {
      if (stoppedGuard.current) return;
      stoppedGuard.current = true;
      const blob = new Blob(chunks.current, { type: mimeRef.current ?? type });
      setVideoBlob(blob);
      setState('stopped');
      teardown();
      onStoppedRef.current?.(blob);
    };

    media.onerror = () => {
      teardown();
      setState('idle');
      setError('Recording failed unexpectedly. Please try again.');
    };

    media.start();
    setState('recording');
    startTime.current = Date.now();
    setElapsed(0);
    setRemaining(null);

    ticker.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime.current) / 1000);
      setElapsed(elapsed);
      const remaining = SNIPPET_MAX_SECONDS - elapsed;
      if (remaining <= SNIPPET_COUNTDOWN_FROM) {
        setRemaining(Math.max(0, remaining));
      } else {
        setRemaining(null);
      }
    }, 200);

    autoStop.current = setTimeout(() => {
      stop();
    }, SNIPPET_MAX_SECONDS * 1000);

    return true;
  }, [stop, teardown]);

  const reset = useCallback(() => {
    stoppedGuard.current = true;
    teardown();
    setState('idle');
    setError(null);
    setElapsed(0);
    setRemaining(null);
    setVideoBlob(null);
    chunks.current = [];
  }, [teardown]);

  useEffect(() => teardown, [teardown]);

  return {
    state,
    error,
    elapsedSeconds,
    secondsRemaining,
    videoBlob,
    stream: streamState,
    start,
    stop,
    reset,
  };
}
