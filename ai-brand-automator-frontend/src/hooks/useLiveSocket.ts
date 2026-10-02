'use client';

/**
 * useLiveSocket — WebSocket connection for LIVE mode (F-06).
 *
 * Connects to the OIA service's WS /v1/live/{sessionId}?ticket=... endpoint.
 * Handles error frames (ERR-07 → degraded status) and recovery frames
 * (→ live status). Binary audio forwarding is exposed via sendBinary().
 *
 * G-02 will extend this to handle transcript and coverage frames.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiClient } from '@/lib/api';

// ── Types ──

/**
 * `reconnecting` is deliberately distinct from `connecting`.
 *
 * Both open a socket, but they mean opposite things to an operator: the first
 * connect is routine, while a reconnect means the live socket dropped
 * mid-meeting and transcription has stopped. They shared one value, so the UI
 * could not tell them apart and showed nothing for either — see #662.
 */
export type LiveSocketStatus =
  | 'idle'
  | 'connecting'
  | 'reconnecting'
  | 'live'
  | 'degraded'
  | 'closed';

export interface LiveSocketError {
  code: string;
  message: string;
  recoverable: boolean;
}

export interface ServerFrame {
  type: string;
  seq?: number;
  text?: string;
  speaker?: number;
  speaker_name?: string;
  [key: string]: unknown;
}

interface UseLiveSocketOptions {
  sessionId: string | null;
  enabled?: boolean;
  onFrame?: (frame: ServerFrame) => void;
}

interface UseLiveSocketReturn {
  status: LiveSocketStatus;
  error: LiveSocketError | null;
  sendBinary: (data: ArrayBuffer | Uint8Array) => void;
  sendControl: (frame: Record<string, unknown>) => void;
}

// ── Constants ──

const BASE = '/onboarding';
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;
/** How long a socket must hold before its reconnect budget is forgiven. */
const STABLE_AFTER_MS = 10_000;
const DEFERRED_CLOSE_MS = 200;

function getOiaWsUrl(sessionId: string, ticket: string): string {
  if (typeof window === 'undefined') return '';
  const { protocol, hostname } = window.location;
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:';
  const tenantId = localStorage.getItem('active_tenant_id') ?? '';
  const qs = `ticket=${ticket}&tenant_id=${tenantId}`;

  if (hostname === 'zorven.ai' || hostname === 'www.zorven.ai') {
    return `${wsProto}//api.zorven.ai/oia/v1/live/${sessionId}?${qs}`;
  }
  if (hostname.includes('.run.app')) {
    return `${wsProto}//zorven-oia-977911773818.us-central1.run.app/v1/live/${sessionId}?${qs}`;
  }
  return `${wsProto}//${hostname}:8120/v1/live/${sessionId}?${qs}`;
}

// ── Hook ──

export function useLiveSocket({
  sessionId,
  enabled = true,
  onFrame,
}: UseLiveSocketOptions): UseLiveSocketReturn {
  const onFrameRef = useRef(onFrame);
  useEffect(() => { onFrameRef.current = onFrame; });
  const [status, setStatus] = useState<LiveSocketStatus>('idle');
  const [error, setError] = useState<LiveSocketError | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const startFrameRef = useRef<Record<string, unknown> | null>(null);
  const deferredCloseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sendBinary = useCallback((data: ArrayBuffer | Uint8Array) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  }, []);

  const sendControl = useCallback((frame: Record<string, unknown>) => {
    // Remember the `start` frame so a reconnect can replay it (#662).
    //
    // The server's STT task belongs to the socket: it is cancelled when the
    // socket closes, and only a `start` frame spawns a new one. Nothing re-sent
    // it, so a dropped socket ended transcription for the rest of the meeting
    // even though the socket itself came back. Caching it here rather than in
    // the recorder keeps the replay next to the reconnect it belongs to.
    //
    // `stop` clears it: the recording is over and replaying start would open an
    // STT stream for a meeting that has ended.
    if (frame.type === 'start') {
      startFrameRef.current = frame;
    } else if (frame.type === 'stop') {
      startFrameRef.current = null;
    }
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(frame));
    }
  }, []);

  useEffect(() => {
    if (!sessionId || !enabled) {
      return;
    }

    // Cancel any deferred close from a prior strict-mode cleanup so we can
    // reuse the existing WebSocket instead of tearing it down and fighting
    // the Redis live lock on reconnect.
    if (deferredCloseRef.current) {
      clearTimeout(deferredCloseRef.current);
      deferredCloseRef.current = null;
    }

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let stableTimer: ReturnType<typeof setTimeout>;

    const handleMessage = (event: MessageEvent) => {
      if (typeof event.data !== 'string') return;
      try {
        const frame = JSON.parse(event.data) as ServerFrame;
        if (frame.type === 'error' && typeof frame.code === 'string') {
          setError({
            code: frame.code as string,
            message: (frame.message as string) || 'Transcription unavailable.',
            recoverable: (frame.recoverable as boolean) ?? false,
          });
          setStatus('degraded');
        } else if (frame.type === 'recovery') {
          setError(null);
          setStatus('live');
        }
        onFrameRef.current?.(frame);
      } catch {
        // Unparseable frame — ignore
      }
    };

    const handleClose = () => {
      wsRef.current = null;
      // Cancel the stability window: this socket did not survive it, and a
      // timer left running would forgive the retry budget on a connection that
      // has already died — which is how a flapping socket never reaches
      // 'closed'.
      clearTimeout(stableTimer);
      if (cancelled) {
        setStatus('closed');
        return;
      }
      if (retriesRef.current < MAX_RECONNECT_ATTEMPTS) {
        retriesRef.current += 1;
        // Not 'connecting': this socket was open and dropped, which stops
        // transcription until a fresh `start` frame is sent. The recorder and
        // the GCS upload are unaffected, so nothing else about the screen
        // changes — which is exactly why this state has to be visible.
        setStatus('reconnecting');
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      } else {
        setStatus('closed');
      }
    };

    const connect = async () => {
      if (cancelled) return;
      // Only the first attempt is 'connecting'. A retry keeps 'reconnecting',
      // or the warning would vanish 3 s in and stay hidden for the rest of a
      // slow attempt — the ticket POST has no timeout and the handshake can
      // hang for tens of seconds, which is exactly when it matters.
      if (retriesRef.current === 0) {
        setStatus('connecting');
      }

      let ticket: string;
      try {
        const response = await apiClient.post(
          `${BASE}/sessions/${sessionId}/live-ticket/`,
          {},
        );
        if (!response.ok) {
          setStatus('closed');
          return;
        }
        const data = await response.json();
        ticket = data.ticket;
      } catch {
        setStatus('closed');
        return;
      }

      if (cancelled) return;

      const url = getOiaWsUrl(sessionId, ticket);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) {
          ws.close();
          return;
        }
        setStatus('live');
        setError(null);

        // Re-arm transcription on the new socket. The server's STT task belongs
        // to the socket and is cancelled when it closes; only a `start` frame
        // spawns another. Without this the socket is back and reports 'live'
        // while the server has no STT task for it, so audio arrives and is
        // dropped — the same silent failure, now behind a reassuring status.
        const resume = startFrameRef.current;
        if (resume) {
          try {
            ws.send(JSON.stringify(resume));
          } catch {
            /* a failed send closes the socket, and the next open retries */
          }
        }

        // Retries are forgiven only once the socket has held for a while. A
        // flapping connection — Cloud Run cutting it repeatedly — would
        // otherwise reset the budget on every open and never reach 'closed'.
        stableTimer = setTimeout(() => {
          retriesRef.current = 0;
        }, STABLE_AFTER_MS);
      };

      ws.onmessage = handleMessage;
      ws.onclose = handleClose;
      ws.onerror = () => {};
    };

    // If the prior mount left a still-usable WebSocket (strict mode), reuse it.
    // Status is already correct from the previous mount (the deferred close's
    // setStatus('idle') was cancelled above), so we only re-attach handlers.
    const existing = wsRef.current;
    if (existing && existing.readyState <= WebSocket.OPEN) {
      retriesRef.current = 0;
      existing.onopen = () => {
        if (cancelled) { existing.close(); return; }
        retriesRef.current = 0;
        setStatus('live');
        setError(null);
      };
      existing.onmessage = handleMessage;
      existing.onclose = handleClose;
      existing.onerror = () => {};
    } else {
      void connect();
    }

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      clearTimeout(stableTimer);
      // Defer the close so a strict-mode remount can cancel it and reuse
      // the connection. A real unmount lets the timer fire after 200 ms.
      deferredCloseRef.current = setTimeout(() => {
        const ws = wsRef.current;
        if (ws) {
          ws.onclose = null;
          ws.close();
          wsRef.current = null;
        }
        setStatus('idle');
      }, DEFERRED_CLOSE_MS);
    };
  }, [sessionId, enabled]);

  return { status, error, sendBinary, sendControl };
}
