'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MessageBubble } from './MessageBubble';
import { ChatHistorySidebar } from './ChatHistorySidebar';
import { ChatInput } from './ChatInput';
import { apiClient } from '@/lib/api';
import { useTenantRole } from '@/hooks/useTenantRole';
import { PanelLeftOpen, PanelLeftClose, ArrowDown } from 'lucide-react';

export interface Attachment {
  id: number;
  file_name: string;
  file_type: string;
  file_size: number;
  pipeline_status: string;
  asset?: number | null;
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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [isLoadingSession, setIsLoadingSession] = useState(false);

  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const titlePollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Clean up title-poll timer on unmount or session change
  useEffect(() => {
    return () => {
      if (titlePollTimerRef.current) {
        clearTimeout(titlePollTimerRef.current);
        titlePollTimerRef.current = null;
      }
    };
  }, [sessionId]);

  // Persist sessionId to localStorage so sidebar can restore it on remount
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('active_chat_session', sessionId);
    }
  }, [sessionId]);

  const handleNewChat = useCallback(() => {
    setSessionId(null);
    setMessages([WELCOME_MESSAGE]);
    localStorage.removeItem('active_chat_session');
  }, []);

  const loadSession = useCallback(async (targetSessionId: string) => {
    setIsLoadingSession(true);
    setSessionId(targetSessionId);

    try {
      // Find the session pk from the sessions list (cache-bust to avoid stale browser cache)
      const sessionsResp = await apiClient.get(
        `/ai/chat-sessions/?_t=${Date.now()}`
      );
      if (!sessionsResp.ok) {
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
        setMessages([WELCOME_MESSAGE]);
        setIsLoadingSession(false);
        return;
      }

      // Load messages
      const msgResp = await apiClient.get(
        `/ai/chat-sessions/${session.id}/messages/`
      );
      if (msgResp.ok) {
        const msgData = await msgResp.json();
        const loaded: Message[] = (
          Array.isArray(msgData) ? msgData : msgData.results ?? []
        ).map(
          (m: {
            id: number;
            role: string;
            content: string;
            thinking?: string;
            metadata?: { job_id?: string };
            attachments?: Attachment[];
            created_at: string;
          }) => ({
            id: String(m.id),
            content: m.content,
            isUser: m.role === 'user',
            timestamp: new Date(m.created_at),
            thinking: m.thinking || '',
            pipelineJobId: m.metadata?.job_id ?? null,
            attachments: m.attachments ?? [],
          })
        );
        setMessages(
          loaded.length > 0 ? loaded : [WELCOME_MESSAGE]
        );
      }
    } catch (err) {
      console.error('Failed to load session:', err);
    }
    setIsLoadingSession(false);
  }, []);

  // Read localStorage once on mount to seed the initial session ID.
  // This prevents the sidebar from auto-selecting a different session.
  const initialSessionRef = useRef<string | null>(
    typeof window !== 'undefined'
      ? localStorage.getItem('active_chat_session')
      : null
  );
  useEffect(() => {
    const saved = initialSessionRef.current;
    if (saved && !sessionId) {
      // Kick off the session load asynchronously — allowed because we
      // only trigger an external fetch, not a synchronous setState cascade.
      (async () => {
        try {
          await loadSession(saved);
        } catch {
          // Session may no longer exist; sidebar auto-select will handle it.
        }
      })();
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

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

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

        const response = await apiClient.post('/ai/chat/', body);

        if (response.ok) {
          const data = await response.json();

          // Persist session_id for conversation continuity
          if (data.session_id && !sessionId) {
            setSessionId(data.session_id);
            setSidebarRefreshKey((k) => k + 1);

            // Auto-titling runs async (Celery/Kafka ~1-2s). Poll the
            // session endpoint until the title changes from the default
            // "Chat ..." placeholder, then refresh the sidebar once.
            // Uses recursive setTimeout to avoid overlapping requests and
            // stores the timer in a ref for cleanup on unmount.
            const newPk = data.session_pk ?? data.session?.id;
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
          }

          const aiMessage: Message = {
            id: (Date.now() + 1).toString(),
            content: data.response || 'I encountered an issue processing your request.',
            isUser: false,
            timestamp: new Date(),
            thinking: data.thinking || '',
            pipelineJobId: data.pipeline_job?.job_id ?? null,
          };
          setMessages((prev) => [...prev, aiMessage]);
          setSidebarRefreshKey((k) => k + 1);
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
    },
    [sessionId]
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
      <div className="flex-1 flex flex-col min-w-0">
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
                  <MessageBubble key={message.id} message={message} />
                ))}
                {isLoading && (
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
          onSend={handleSend}
          disabled={!canEdit}
          isLoading={isLoading}
          placeholder="Ask me about your brand strategy..."
          disabledTitle={!canEdit ? 'You need editor access to use the AI chat' : undefined}
        />
      </div>
    </div>
  );
}
