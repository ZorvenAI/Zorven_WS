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

export type LiveSocketStatus = 'idle' | 'connecting' | 'live' | 'degraded' | 'closed';

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
  onFrameRef.current = onFrame;
  const [status, setStatus] = useState<LiveSocketStatus>('idle');
  const [error, setError] = useState<LiveSocketError | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const deferredCloseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sendBinary = useCallback((data: ArrayBuffer | Uint8Array) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  }, []);

  const sendControl = useCallback((frame: Record<string, unknown>) => {
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
      if (cancelled) {
        setStatus('closed');
        return;
      }
      if (retriesRef.current < MAX_RECONNECT_ATTEMPTS) {
        retriesRef.current += 1;
        setStatus('connecting');
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      } else {
        setStatus('closed');
      }
    };

    const connect = async () => {
      if (cancelled) return;
      setStatus('connecting');

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
        retriesRef.current = 0;
        setStatus('live');
        setError(null);
      };

      ws.onmessage = handleMessage;
      ws.onclose = handleClose;
      ws.onerror = () => {};
    };

    // If the prior mount left a still-usable WebSocket (strict mode), reuse it
    const existing = wsRef.current;
    if (existing && existing.readyState <= WebSocket.OPEN) {
      if (existing.readyState === WebSocket.OPEN) {
        retriesRef.current = 0;
        setStatus('live');
        setError(null);
      } else {
        setStatus('connecting');
      }
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
