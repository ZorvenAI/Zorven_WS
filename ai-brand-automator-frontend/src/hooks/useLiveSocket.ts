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

interface UseLiveSocketOptions {
  sessionId: string | null;
  enabled?: boolean;
}

interface UseLiveSocketReturn {
  status: LiveSocketStatus;
  error: LiveSocketError | null;
  sendBinary: (data: ArrayBuffer | Uint8Array) => void;
  sendControl: (frame: Record<string, unknown>) => void;
}

// ── Constants ──

const BASE = '/api/v1/onboarding';
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

function getOiaWsUrl(sessionId: string, ticket: string): string {
  if (typeof window === 'undefined') return '';
  const { protocol, hostname } = window.location;
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:';

  if (hostname === 'zorven.ai' || hostname === 'www.zorven.ai') {
    return `${wsProto}//api.zorven.ai/oia/v1/live/${sessionId}?ticket=${ticket}`;
  }
  if (hostname.includes('.run.app')) {
    return `${wsProto}//zorven-oia-977911773818.us-central1.run.app/v1/live/${sessionId}?ticket=${ticket}`;
  }
  return `${wsProto}//${hostname}:8120/v1/live/${sessionId}?ticket=${ticket}`;
}

// ── Hook ──

export function useLiveSocket({
  sessionId,
  enabled = true,
}: UseLiveSocketOptions): UseLiveSocketReturn {
  const [status, setStatus] = useState<LiveSocketStatus>('idle');
  const [error, setError] = useState<LiveSocketError | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);

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
      setStatus('idle');
      return;
    }

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;

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

      ws.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        try {
          const frame = JSON.parse(event.data) as Record<string, unknown>;
          if (frame.type === 'error' && typeof frame.code === 'string') {
            setError({
              code: frame.code as string,
              message: (frame.message as string) || 'Transcription unavailable.',
              recoverable: (frame.recoverable as boolean) ?? false,
            });
            if (frame.recoverable) {
              setStatus('degraded');
            }
          } else if (frame.type === 'recovery') {
            setError(null);
            setStatus('live');
          }
        } catch {
          // Unparseable frame — ignore
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (cancelled) {
          setStatus('closed');
          return;
        }
        if (retriesRef.current < MAX_RECONNECT_ATTEMPTS) {
          retriesRef.current += 1;
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        } else {
          setStatus('closed');
        }
      };

      ws.onerror = () => {
        // onclose fires after onerror, so reconnect logic lives there
      };
    };

    void connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null;
        ws.close();
        wsRef.current = null;
      }
      setStatus('idle');
    };
  }, [sessionId, enabled]);

  return { status, error, sendBinary, sendControl };
}
