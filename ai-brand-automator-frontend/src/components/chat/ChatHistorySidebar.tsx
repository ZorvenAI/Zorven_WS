'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { Plus, Trash2, MessageSquare, Loader2 } from 'lucide-react';

interface ChatSessionSummary {
  id: number;
  session_id: string;
  title: string;
  last_message_preview: string;
  message_count: number;
  last_activity: string;
  created_at: string;
}

interface ChatHistorySidebarProps {
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  refreshKey?: number;
}

function groupByDate(sessions: ChatSessionSummary[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: { label: string; sessions: ChatSessionSummary[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Previous 7 days', sessions: [] },
    { label: 'Older', sessions: [] },
  ];

  for (const session of sessions) {
    const date = new Date(session.last_activity);
    if (date >= today) {
      groups[0].sessions.push(session);
    } else if (date >= yesterday) {
      groups[1].sessions.push(session);
    } else if (date >= weekAgo) {
      groups[2].sessions.push(session);
    } else {
      groups[3].sessions.push(session);
    }
  }

  return groups.filter((g) => g.sessions.length > 0);
}

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const date = new Date(dateStr).getTime();
  const diff = now - date;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function ChatHistorySidebar({
  activeSessionId,
  onSelectSession,
  onNewChat,
  refreshKey,
}: ChatHistorySidebarProps) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await apiClient.get('/ai/chat-sessions/');
      if (response.ok) {
        const data = await response.json();
        const list = Array.isArray(data) ? data : data.results ?? [];
        setSessions(list);
      }
    } catch (err) {
      console.error('Failed to fetch chat sessions:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions, refreshKey]);

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleteConfirm !== sessionId) {
      setDeleteConfirm(sessionId);
      return;
    }
    // Confirmed delete
    const session = sessions.find((s) => s.session_id === sessionId);
    if (!session) return;

    try {
      const response = await apiClient.delete(
        `/ai/chat-sessions/${session.id}/`
      );
      if (response.ok) {
        setSessions((prev) =>
          prev.filter((s) => s.session_id !== sessionId)
        );
        if (activeSessionId === sessionId) {
          onNewChat();
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
    setDeleteConfirm(null);
  };

  const groups = groupByDate(sessions);

  return (
    <div className="flex flex-col h-full">
      {/* New Chat button */}
      <div className="p-3 border-b border-white/10">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 hover:bg-white/5 text-sm text-brand-silver transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-brand-silver/50">
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8 text-brand-silver/40 text-xs">
            No conversations yet
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-3">
              <div className="px-2 py-1 text-xs font-medium text-brand-silver/40 uppercase tracking-wider">
                {group.label}
              </div>
              {group.sessions.map((session) => {
                const isActive = activeSessionId === session.session_id;
                return (
                  <button
                    key={session.session_id}
                    onClick={() => onSelectSession(session.session_id)}
                    onBlur={() => {
                      if (deleteConfirm === session.session_id) {
                        setTimeout(() => setDeleteConfirm(null), 200);
                      }
                    }}
                    className={`group w-full text-left px-2 py-2 rounded-lg mb-0.5 transition-colors ${
                      isActive
                        ? 'bg-white/10 text-white'
                        : 'text-brand-silver hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 opacity-50" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-sm truncate font-medium">
                            {session.title || 'Untitled'}
                          </span>
                          <button
                            onClick={(e) =>
                              handleDelete(session.session_id, e)
                            }
                            className={`shrink-0 p-0.5 rounded transition-colors ${
                              deleteConfirm === session.session_id
                                ? 'text-red-400 opacity-100'
                                : 'text-brand-silver/30 opacity-0 group-hover:opacity-100 hover:text-red-400'
                            }`}
                            title={
                              deleteConfirm === session.session_id
                                ? 'Click again to confirm'
                                : 'Delete'
                            }
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                        {session.last_message_preview && (
                          <p className="text-xs text-brand-silver/40 truncate mt-0.5">
                            {session.last_message_preview}
                          </p>
                        )}
                        <p className="text-[10px] text-brand-silver/30 mt-0.5">
                          {timeAgo(session.last_activity)}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
