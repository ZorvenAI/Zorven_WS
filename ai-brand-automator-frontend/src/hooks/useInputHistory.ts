'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { apiClient } from '@/lib/api';

interface UseInputHistoryOptions {
  sessionId: string | null;
  sessionPk: number | null;
}

export function useInputHistory({ sessionId, sessionPk }: UseInputHistoryOptions) {
  const [history, setHistory] = useState<string[]>(() => {
    if (!sessionId) return [];
    try {
      const stored = localStorage.getItem(`chat_input_history_${sessionId}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch {
      // Ignore parse errors
    }
    return [];
  });
  const [cursor, setCursor] = useState(-1);
  const draftRef = useRef('');
  const [prevSessionId, setPrevSessionId] = useState(sessionId);

  // Derived-state-from-props pattern (React-recommended replacement for
  // getDerivedStateFromProps). setState during render is explicitly
  // supported by React for this use case.
  if (sessionId !== prevSessionId) {
    setPrevSessionId(sessionId);
    setCursor(-1);

    let loaded: string[] = [];
    if (sessionId) {
      try {
        const stored = localStorage.getItem(`chat_input_history_${sessionId}`);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed)) {
            loaded = parsed;
          }
        }
      } catch {
        // Ignore parse errors
      }
    }
    setHistory(loaded);
  }

  // Hydrate from API (async — setState in callback is fine)
  useEffect(() => {
    if (!sessionId || !sessionPk) return;

    let cancelled = false;
    (async () => {
      try {
        const resp = await apiClient.get(
          `/ai/chat-sessions/${sessionPk}/input-history/`
        );
        if (resp.ok && !cancelled) {
          const data = await resp.json();
          if (Array.isArray(data.history) && data.history.length > 0) {
            setHistory(data.history);
            try {
              localStorage.setItem(
                `chat_input_history_${sessionId}`,
                JSON.stringify(data.history)
              );
            } catch {
              // localStorage full or unavailable
            }
          }
        }
      } catch {
        // API call failed — use localStorage data
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, sessionPk]);

  const pushMessage = useCallback(
    (msg: string) => {
      if (!msg.trim() || !sessionId) return;

      setHistory((prev) => {
        const updated = [...prev, msg].slice(-50); // cap at 50
        try {
          localStorage.setItem(
            `chat_input_history_${sessionId}`,
            JSON.stringify(updated)
          );
        } catch {
          // localStorage full
        }
        return updated;
      });
      setCursor(-1);
    },
    [sessionId]
  );

  const navigateUp = useCallback((): string | null => {
    if (history.length === 0) return null;

    const newCursor = cursor === -1 ? history.length - 1 : cursor - 1;
    if (newCursor < 0) return null;

    setCursor(newCursor);
    return history[newCursor];
  }, [history, cursor]);

  const navigateDown = useCallback((): string | null => {
    if (cursor === -1) return null;

    const newCursor = cursor + 1;
    if (newCursor >= history.length) {
      setCursor(-1);
      return draftRef.current;
    }

    setCursor(newCursor);
    return history[newCursor];
  }, [history, cursor]);

  const exitHistory = useCallback(() => {
    setCursor(-1);
  }, []);

  const setCurrentDraft = useCallback((text: string) => {
    // Only save draft when not browsing history
    draftRef.current = text;
  }, []);

  return {
    history,
    pushMessage,
    navigateUp,
    navigateDown,
    exitHistory,
    setCurrentDraft,
  };
}
