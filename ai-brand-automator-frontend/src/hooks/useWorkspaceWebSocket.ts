/**
 * useWorkspaceWebSocket — real-time WebSocket connection for workspace
 * pipeline progress updates.
 *
 * Connects to ws://<host>/ws/workspace/<tenantId>/?token=<jwt>
 * Auto-reconnects with exponential backoff (1s → 2s → 4s, max 30s).
 * Falls back gracefully — components can always use usePollingJob as backup.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import type { AgentProgress, JobStatus } from '@/types/orchestration';

// ── Types ──

export interface WorkspaceWSEvent {
  type: 'job_progress' | 'job_completed';
  data: {
    job_id: string;
    status: JobStatus;
    current_node: string | null;
    progress_percent: number;
    progress: Record<string, AgentProgress>;
    error_message?: string;
  };
}

type EventHandler = (event: WorkspaceWSEvent) => void;

interface UseWorkspaceWebSocketOptions {
  /** Tenant ID to connect to. */
  tenantId: number | null;
  /** Called on every incoming event. */
  onEvent?: EventHandler;
  /** Disable the connection (e.g. when no active jobs). */
  enabled?: boolean;
}

interface UseWorkspaceWebSocketReturn {
  /** Whether the WebSocket is currently connected. */
  isConnected: boolean;
  /** Last connection error message, if any. */
  error: string | null;
}

// ── Constants ──

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const BACKOFF_MULTIPLIER = 2;
const PING_INTERVAL_MS = 30000;

// ── Hook ──

export function useWorkspaceWebSocket({
  tenantId,
  onEvent,
  enabled = true,
}: UseWorkspaceWebSocketOptions): UseWorkspaceWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onEventRef = useRef(onEvent);

  // Keep callback ref fresh without accessing during render
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  // Store connect in a ref so the onclose handler can call it without
  // creating a circular dependency.
  const connectRef = useRef<() => void>(() => {});

  useEffect(() => {
    connectRef.current = () => {
      if (!tenantId || !enabled) return;

      // Get JWT token
      const token = typeof window !== 'undefined'
        ? localStorage.getItem('access_token')
        : null;
      if (!token) {
        setError('No access token available');
        return;
      }

      // Build WebSocket URL — routes through Kong (:8000) which proxies to
      // backend-ws (:8002). In production, NEXT_PUBLIC_WS_URL should be set to
      // the Kong gateway's wss:// URL.
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = process.env.NEXT_PUBLIC_WS_URL
        || `${protocol}//${window.location.hostname}:8000`;
      const url = `${host}/ws/workspace/${tenantId}/?token=${token}`;

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          setError(null);
          backoffRef.current = INITIAL_BACKOFF_MS;

          // Start ping interval to keep connection alive
          pingTimerRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }));
            }
          }, PING_INTERVAL_MS);
        };

        ws.onmessage = (event) => {
          try {
            const raw = JSON.parse(event.data) as { type: string; data?: unknown };
            if (raw.type === 'pong') return;
            onEventRef.current?.(raw as WorkspaceWSEvent);
          } catch {
            // Ignore malformed messages
          }
        };

        ws.onerror = () => {
          setError('WebSocket connection error');
        };

        ws.onclose = (closeEvent) => {
          setIsConnected(false);
          if (pingTimerRef.current) {
            clearInterval(pingTimerRef.current);
            pingTimerRef.current = null;
          }

          // Don't reconnect if intentionally closed or disabled
          if (!enabled || closeEvent.code === 1000) return;

          // Exponential backoff reconnect
          const delay = backoffRef.current;
          backoffRef.current = Math.min(
            backoffRef.current * BACKOFF_MULTIPLIER,
            MAX_BACKOFF_MS,
          );
          reconnectTimerRef.current = setTimeout(() => connectRef.current(), delay);
        };
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to connect');
      }
    };
  }, [tenantId, enabled]);

  useEffect(() => {
    // Cleanup helper
    const doCleanup = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
    };

    if (!enabled || !tenantId) {
      doCleanup();
      return;
    }

    connectRef.current();

    return () => {
      doCleanup();
    };
  }, [tenantId, enabled]);

  return { isConnected, error };
}
