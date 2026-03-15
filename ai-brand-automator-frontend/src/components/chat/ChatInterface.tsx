'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
import { MessageBubble } from './MessageBubble';
import { ChatHistorySidebar } from './ChatHistorySidebar';
import { ChatInput } from './ChatInput';
import type { ChatInputHandle } from './ChatInput';
import { apiClient } from '@/lib/api';
import { getJobQuickStatus } from '@/lib/orchestration';
import { cancelJob } from '@/lib/orchestration';
import { useTenantRole } from '@/hooks/useTenantRole';
import { useInputHistory } from '@/hooks/useInputHistory';
import { useSearchParams } from 'next/navigation';
import { PanelLeftOpen, PanelLeftClose, ArrowDown, Upload } from 'lucide-react';

export interface Attachment {
  id: number;
  file_name: string;
  file_type: string;
  file_size: number;
  pipeline_status: string;
  asset?: number | null;
  thumbnail_url?: string | null;
}

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
  thinking?: string;
  pipelineJobId?: string | null;
  attachments?: Attachment[];
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  content:
    "Hello! I'm BranSol AI your brand assistant. How can I help you with your brand strategy today?",
  isUser: false,
  timestamp: new Date(),
};

export function ChatInterface() {
  const { canEdit: canEditFlag } = useTenantRole();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => {
    requestAnimationFrame(() => setHasMounted(true));
  }, []);
  const canEdit = hasMounted ? canEditFlag : false;

  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  // Start null — localStorage is read in the mount effect (not useState) to avoid
  // SSR/hydration issues where the server returns null and React reuses it.
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionPk, setSessionPk] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [pendingMessage, setPendingMessage] = useState('');
  const [initialInputValue, setInitialInputValue] = useState<string | undefined>(undefined);

  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const titlePollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const dragCounterRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  const activePipelineJobIdRef = useRef<string | null>(null);
  const pipelinePollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const isLoadingSessionRef = useRef(false);

  // Input history hook
  const inputHistory = useInputHistory({ sessionId, sessionPk });

  // Track scroll position to show/hide scroll-to-bottom button
  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(distFromBottom > 100);
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Full-area drag-and-drop handlers (counter pattern to avoid flicker)
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      chatInputRef.current?.addFiles(e.dataTransfer.files);
    }
  }, []);

  // Poll a pipeline job until terminal state, then release isLoading
  const startPipelinePolling = useCallback((jobId: string) => {
    activePipelineJobIdRef.current = jobId;
    setIsPipelineRunning(true);

    const poll = async () => {
      // Job was cancelled or replaced — stop polling
      if (activePipelineJobIdRef.current !== jobId) return;

      try {
        const qs = await getJobQuickStatus(jobId);
        if (activePipelineJobIdRef.current !== jobId) return;

        if (qs.status === 'completed' || qs.status === 'failed') {
          activePipelineJobIdRef.current = null;
          pipelinePollTimerRef.current = null;
          setIsPipelineRunning(false);
          setIsLoading(false);
          return;
        }
      } catch {
        // Retry on error — don't drop the loading state
      }

      pipelinePollTimerRef.current = setTimeout(poll, 3000);
    };

    // First poll after a short delay (pipeline needs a moment to register)
    pipelinePollTimerRef.current = setTimeout(poll, 2000);
  }, []);

  // Cleanup pipeline poll timer on unmount or session change
  useEffect(() => {
    return () => {
      if (pipelinePollTimerRef.current) {
        clearTimeout(pipelinePollTimerRef.current);
        pipelinePollTimerRef.current = null;
      }
      activePipelineJobIdRef.current = null;
      setIsPipelineRunning(false);
      setIsLoading(false);
    };
  }, [sessionId]);

  // Clean up title-poll timer on unmount or session change
  useEffect(() => {
    return () => {
      if (titlePollTimerRef.current) {
        clearTimeout(titlePollTimerRef.current);
        titlePollTimerRef.current = null;
      }
    };
  }, [sessionId]);

  // Persist sessionId and sessionPk to localStorage so we can restore on remount
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('active_chat_session', sessionId);
    }
    if (sessionPk) {
      localStorage.setItem('active_chat_session_pk', String(sessionPk));
    }
  }, [sessionId, sessionPk]);

  const handleNewChat = useCallback(() => {
    setSessionId(null);
    setSessionPk(null);
    setMessages([WELCOME_MESSAGE]);
    localStorage.removeItem('active_chat_session');
    localStorage.removeItem('active_chat_session_pk');
  }, []);

  const loadSession = useCallback(async (targetSessionId: string, savedPk?: number) => {
    isLoadingSessionRef.current = true;
    setIsLoadingSession(true);
    setSessionId(targetSessionId);

    try {
      let pk = savedPk;

      // Strategy 1: Use saved PK for direct session lookup (fast, no pagination issues)
      if (pk) {
        const directResp = await apiClient.get(
          `/ai/chat-sessions/${pk}/?_t=${Date.now()}`
        );
        if (directResp.ok) {
          const sessionData = await directResp.json();
          if (sessionData.session_id !== targetSessionId) {
            pk = undefined; // PK is stale, fall through to list lookup
          }
        } else {
          pk = undefined;
        }
      }

      // Strategy 2: Fall back to sessions list lookup
      if (!pk) {
        const sessionsResp = await apiClient.get(
          `/ai/chat-sessions/?_t=${Date.now()}`
        );
        if (!sessionsResp.ok) {
          isLoadingSessionRef.current = false;
          setIsLoadingSession(false);
          return;
        }
        const sessionsData = await sessionsResp.json();
        const list = Array.isArray(sessionsData)
          ? sessionsData
          : sessionsData.results ?? [];
        const session = list.find(
          (s: { session_id: string }) =>
            s.session_id === targetSessionId
        );
        if (!session) {
          // Session no longer exists — clear stale reference
          setSessionId(null);
          setSessionPk(null);
          setMessages([WELCOME_MESSAGE]);
          localStorage.removeItem('active_chat_session');
          localStorage.removeItem('active_chat_session_pk');
          isLoadingSessionRef.current = false;
          setIsLoadingSession(false);
          return;
        }
        pk = session.id;
      }

      setSessionPk(pk as number);

      // Load ALL message pages (DRF paginates at PAGE_SIZE=20).
      // Messages are ordered ascending by created_at, so page 1 is oldest.
      // Fetch all pages to ensure the most recent messages are included.
      type RawMessage = {
        id: number;
        role: string;
        content: string;
        thinking?: string;
        metadata?: { job_id?: string };
        attachments?: Attachment[];
        created_at: string;
      };
      let allRaw: RawMessage[] = [];
      let nextUrl: string | null = `/ai/chat-sessions/${pk}/messages/?_t=${Date.now()}`;

      while (nextUrl) {
        const msgResp = await apiClient.get(nextUrl);
        if (!msgResp.ok) break;
        const msgData = await msgResp.json();

        if (Array.isArray(msgData)) {
          // Non-paginated response
          allRaw = msgData;
          break;
        }

        const results: RawMessage[] = msgData.results ?? [];
        allRaw = [...allRaw, ...results];

        // DRF returns absolute URLs for `next` (e.g.
        // http://localhost:8000/api/v1/ai/chat-sessions/109/messages/?page=2).
        // apiClient.get() already prepends /api/v1, so strip it to avoid
        // a doubled /api/v1/api/v1/... prefix that causes 404s.
        if (msgData.next) {
          try {
            const parsed = new URL(msgData.next);
            let path = parsed.pathname + parsed.search;
            path = path.replace(/^\/api\/v1/, '');
            nextUrl = path;
          } catch {
            nextUrl = null;
          }
        } else {
          nextUrl = null;
        }
      }

      const loaded: Message[] = allRaw.map((m) => ({
        id: String(m.id),
        content: m.content,
        isUser: m.role === 'user',
        timestamp: new Date(m.created_at),
        thinking: m.thinking || '',
        pipelineJobId: m.metadata?.job_id ?? null,
        attachments: m.attachments ?? [],
      }));

      setMessages(loaded.length > 0 ? loaded : [WELCOME_MESSAGE]);
    } catch {
      // Network error — keep whatever state we have
      isLoadingSessionRef.current = false;
    }
    setIsLoadingSession(false);
  }, []);

  // Support ?session= query param for shared links (takes priority over localStorage)
  const searchParams = useSearchParams();
  const querySessionId = useMemo(
    () => searchParams.get('session'),
    [searchParams]
  );

  // On mount: restore session from query param, localStorage, or auto-select most recent.
  // All session selection logic lives here — the sidebar never auto-selects.
  // We read localStorage HERE (not in useState) to avoid SSR hydration issues.
  // Guard: React StrictMode double-mounts in dev — skip if loadSession is already running.
  useEffect(() => {
    if (isLoadingSessionRef.current) return;

    const savedId = localStorage.getItem('active_chat_session');
    const savedPkStr = localStorage.getItem('active_chat_session_pk');
    const savedPk = savedPkStr ? Number(savedPkStr) : undefined;
    const target = querySessionId || savedId;

    if (target) {
      loadSession(target, savedPk).catch(() => {});
    } else {
      // No saved session — auto-select the most recent one
      apiClient
        .get(`/ai/chat-sessions/?_t=${Date.now()}`)
        .then(async (resp) => {
          if (!resp.ok) return;
          const data = await resp.json();
          const list = Array.isArray(data) ? data : data.results ?? [];
          if (list.length > 0) {
            const sorted = [...list].sort(
              (a: { last_activity: string }, b: { last_activity: string }) =>
                new Date(b.last_activity).getTime() -
                new Date(a.last_activity).getTime()
            );
            await loadSession(sorted[0].session_id, sorted[0].id);
          }
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      if (selectedSessionId === sessionId) return;
      await loadSession(selectedSessionId);
    },
    [sessionId, loadSession]
  );

  // Instant scroll-to-bottom when a loaded session becomes visible.
  // useLayoutEffect fires before paint, preventing a visual flash at the wrong position.
  // A MutationObserver re-scrolls as child content settles (markdown rendering, images, etc.).
  useLayoutEffect(() => {
    if (isLoadingSession || !isLoadingSessionRef.current) return;
    isLoadingSessionRef.current = false;

    const el = messagesContainerRef.current;
    if (!el) return;

    const jumpToBottom = () => {
      el.scrollTop = el.scrollHeight;
    };

    // Immediate scroll before paint
    jumpToBottom();

    // Re-scroll whenever child content changes (react-markdown, syntax highlighting,
    // image loads, PipelineInlineCard status updates). Auto-disconnect after 3s.
    const observer = new MutationObserver(jumpToBottom);
    observer.observe(el, { childList: true, subtree: true, attributes: true, characterData: true });

    const disconnectTimer = setTimeout(() => observer.disconnect(), 3000);

    return () => {
      observer.disconnect();
      clearTimeout(disconnectTimer);
    };
  }, [messages, isLoadingSession]);

  // Smooth scroll on new messages during conversation
  useEffect(() => {
    if (isLoadingSession || isLoadingSessionRef.current) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, isLoadingSession]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);

    // Abort the in-flight fetch
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // Stop pipeline polling
    if (pipelinePollTimerRef.current) {
      clearTimeout(pipelinePollTimerRef.current);
      pipelinePollTimerRef.current = null;
    }

    // Best-effort cancel on backend (chat + pipeline)
    const pipelineJobId = activePipelineJobIdRef.current;
    activePipelineJobIdRef.current = null;

    if (sessionId) {
      try {
        await apiClient.post('/ai/chat/cancel/', { session_id: sessionId });
      } catch {
        // Ignore — cancel is best-effort
      }
    }

    if (pipelineJobId) {
      try {
        await cancelJob(pipelineJobId);
      } catch {
        // Ignore — cancel is best-effort
      }
    }

    // Remove the last user message (it wasn't processed)
    setMessages((prev) => {
      const lastUserIdx = [...prev].reverse().findIndex((m) => m.isUser);
      if (lastUserIdx !== -1) {
        const idx = prev.length - 1 - lastUserIdx;
        return [...prev.slice(0, idx), ...prev.slice(idx + 1)];
      }
      return prev;
    });

    setIsPipelineRunning(false);
    setIsLoading(false);
    setIsCancelling(false);
    // Restore the pending message to the input
    setInitialInputValue(pendingMessage);
  }, [sessionId, pendingMessage]);

  const handleSend = useCallback(
    async (message: string, files: File[]) => {
      if (!message.trim() && files.length === 0) return;

      const userMessage: Message = {
        id: Date.now().toString(),
        content: message || (files.length > 0 ? `Attached ${files.length} file(s)` : ''),
        isUser: true,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setPendingMessage(message);
      setInitialInputValue(undefined);

      // Create AbortController for this request
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        // Upload files FIRST so attachment IDs can be sent with the message
        const attachmentIds: number[] = [];
        let uploadSessionId = sessionId;

        if (files.length > 0) {
          // For new conversations, create session first via a lightweight chat call
          if (!uploadSessionId) {
            const initResp = await apiClient.post('/ai/chat/', {
              message: 'Starting new conversation',
            });
            if (initResp.ok) {
              const initData = await initResp.json();
              uploadSessionId = initData.session_id;
              if (uploadSessionId) {
                setSessionId(uploadSessionId);
                setSessionPk(initData.session_pk ?? initData.session?.id ?? null);
                setSidebarRefreshKey((k) => k + 1);
              }
            }
          }

          if (uploadSessionId) {
            for (const file of files) {
              const formData = new FormData();
              formData.append('file', file);
              formData.append('session_id', uploadSessionId);
              try {
                const uploadResp = await apiClient.upload('/ai/chat/upload/', formData);
                if (uploadResp.ok) {
                  const uploadData = await uploadResp.json();
                  if (uploadData.id) {
                    attachmentIds.push(uploadData.id);
                  }
                }
              } catch (err) {
                console.error('File upload failed:', err);
              }
            }
          }
        }

        // Send message WITH attachment_ids
        const body: Record<string, unknown> = {
          message: message || 'Attached files for analysis',
        };
        if (uploadSessionId || sessionId) {
          body.session_id = uploadSessionId || sessionId;
        }
        if (attachmentIds.length > 0) {
          body.attachment_ids = attachmentIds;
        }

        const response = await apiClient.postWithSignal(
          '/ai/chat/',
          body,
          controller.signal
        );

        if (response.ok) {
          const data = await response.json();

          // Persist session_id for conversation continuity
          if (data.session_id && !sessionId) {
            setSessionId(data.session_id);
            const newPk = data.session_pk ?? data.session?.id;
            if (newPk) {
              setSessionPk(newPk);
            }
            setSidebarRefreshKey((k) => k + 1);

            // Auto-titling runs async (Celery/Kafka ~1-2s). Poll the
            // session endpoint until the title changes from the default
            // "Chat ..." placeholder, then refresh the sidebar once.
            // Uses recursive setTimeout to avoid overlapping requests and
            // stores the timer in a ref for cleanup on unmount.
            if (newPk) {
              let attempts = 0;
              const pollOnce = async () => {
                attempts++;
                try {
                  const r = await apiClient.get(
                    `/ai/chat-sessions/${newPk}/?_t=${Date.now()}`
                  );
                  if (r.ok) {
                    const s = await r.json();
                    if (s.title && !s.title.startsWith('Chat ')) {
                      titlePollTimerRef.current = null;
                      setSidebarRefreshKey((k) => k + 1);
                      return;
                    }
                  }
                } catch { /* ignore */ }
                if (attempts < 5) {
                  titlePollTimerRef.current = setTimeout(pollOnce, 2000);
                } else {
                  titlePollTimerRef.current = null;
                }
              };
              titlePollTimerRef.current = setTimeout(pollOnce, 2000);
            }
          } else if (data.session_pk ?? data.session?.id) {
            // Update sessionPk for existing sessions
            setSessionPk(data.session_pk ?? data.session?.id);
          }

          // Push to input history after successful send
          inputHistory.pushMessage(message);

          const pipelineJobId = data.pipeline_job?.job_id ?? null;

          const aiMessage: Message = {
            id: (Date.now() + 1).toString(),
            content: data.response || 'I encountered an issue processing your request.',
            isUser: false,
            timestamp: new Date(),
            thinking: data.thinking || '',
            pipelineJobId,
          };
          setMessages((prev) => [...prev, aiMessage]);
          setSidebarRefreshKey((k) => k + 1);

          // If a pipeline was dispatched, start polling for progress.
          // isPipelineRunning tracks the pipeline state independently;
          // isLoading is cleared below so the typing indicator disappears
          // once the AI response is rendered.
          if (pipelineJobId) {
            abortControllerRef.current = null;
            startPipelinePolling(pipelineJobId);
          }
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: (Date.now() + 1).toString(),
              content: 'Sorry, I encountered an error. Please try again.',
              isUser: false,
              timestamp: new Date(),
            },
          ]);
        }
      } catch (error) {
        // Don't show error message if the request was aborted (user cancelled)
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        console.error('AI chat error:', error);
        setMessages((prev) => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            content: 'Sorry, I encountered an error. Please try again.',
            isUser: false,
            timestamp: new Date(),
          },
        ]);
      }
      setIsLoading(false);
      abortControllerRef.current = null;
    },
    [sessionId, inputHistory, startPipelinePolling]
  );

  if (!hasMounted) {
    return (
      <div className="flex h-full items-center justify-center bg-brand-midnight">
        <div className="w-5 h-5 border-2 border-brand-electric/30 border-t-brand-electric rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat History Sidebar — left side, Gemini-style */}
      {sidebarOpen && (
        <div className="hidden md:flex w-64 lg:w-72 shrink-0 bg-brand-midnight border-r border-white/10 flex-col">
          <ChatHistorySidebar
            activeSessionId={sessionId}
            onSelectSession={handleSelectSession}
            onNewChat={handleNewChat}
            refreshKey={sidebarRefreshKey}
          />
        </div>
      )}

      {/* Chat Area */}
      <div
        className="flex-1 flex flex-col min-w-0 relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Header */}
        <div className="shrink-0 bg-brand-midnight/80 backdrop-blur border-b border-white/10 px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="hidden md:flex p-1.5 rounded-lg hover:bg-white/5 text-brand-silver/60 hover:text-white transition-colors"
              title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              {sidebarOpen ? (
                <PanelLeftClose className="w-4 h-4" />
              ) : (
                <PanelLeftOpen className="w-4 h-4" />
              )}
            </button>
            <div>
              <h1 className="text-lg sm:text-xl font-heading font-semibold text-white truncate">
                AI Brand Assistant
              </h1>
              <p className="text-xs sm:text-sm text-brand-silver/70 hidden sm:block">
                Ask anything about your brand or run an analysis pipeline
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="relative flex-1 overflow-hidden">
          <div
            ref={messagesContainerRef}
            onScroll={handleScroll}
            className="h-full overflow-y-auto px-4 sm:px-6 py-4 space-y-4 bg-brand-midnight"
          >
            {isLoadingSession ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-5 h-5 border-2 border-brand-electric/30 border-t-brand-electric rounded-full animate-spin" />
              </div>
            ) : (
              <>
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} chatSessionId={sessionId} />
                ))}
                {isLoading && !isPipelineRunning && (
                  <div className="flex justify-start">
                    <div className="bg-white/5 border border-white/10 rounded-lg px-4 py-2">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-brand-electric rounded-full animate-bounce" />
                        <div
                          className="w-2 h-2 bg-brand-electric rounded-full animate-bounce"
                          style={{ animationDelay: '0.1s' }}
                        />
                        <div
                          className="w-2 h-2 bg-brand-electric rounded-full animate-bounce"
                          style={{ animationDelay: '0.2s' }}
                        />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Scroll to bottom button */}
          {showScrollBtn && (
            <button
              onClick={scrollToBottom}
              className="absolute bottom-4 left-1/2 -translate-x-1/2 p-2 rounded-full bg-white/10 border border-white/10 text-brand-silver/60 hover:bg-white/20 hover:text-white transition-all shadow-lg"
              title="Scroll to bottom"
            >
              <ArrowDown className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Input */}
        <ChatInput
          ref={chatInputRef}
          onSend={handleSend}
          onCancel={handleCancel}
          disabled={!canEdit}
          isLoading={isLoading || isPipelineRunning}
          isCancelling={isCancelling}
          placeholder="Ask me about your brand strategy..."
          disabledTitle={!canEdit ? 'You need editor access to use the AI chat' : undefined}
          initialValue={initialInputValue}
          onNavigateUp={inputHistory.navigateUp}
          onNavigateDown={inputHistory.navigateDown}
          onExitHistory={inputHistory.exitHistory}
          onDraftChange={inputHistory.setCurrentDraft}
        />

        {/* Full-area drop zone overlay */}
        {isDragging && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-brand-midnight/80 backdrop-blur-sm border-2 border-dashed border-brand-electric/50 rounded-lg pointer-events-none">
            <div className="flex flex-col items-center gap-3 text-brand-electric">
              <Upload className="w-10 h-10" />
              <p className="text-lg font-semibold">Drop files here</p>
              <p className="text-sm text-brand-silver/60">Images, PDFs, documents up to 50MB</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
