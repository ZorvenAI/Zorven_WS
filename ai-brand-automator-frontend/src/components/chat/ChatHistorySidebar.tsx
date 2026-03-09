'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '@/lib/api';
import {
  Plus,
  Trash2,
  MessageSquare,
  Loader2,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Link2,
  Check,
} from 'lucide-react';

interface ChatSessionSummary {
  id: number;
  session_id: string;
  title: string;
  is_pinned: boolean;
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

  const pinned = sessions.filter((s) => s.is_pinned);
  const unpinned = sessions.filter((s) => !s.is_pinned);

  const groups: { label: string; sessions: ChatSessionSummary[] }[] = [];

  if (pinned.length > 0) {
    groups.push({ label: 'Pinned', sessions: pinned });
  }

  const dateGroups: { label: string; sessions: ChatSessionSummary[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Previous 7 days', sessions: [] },
    { label: 'Older', sessions: [] },
  ];

  for (const session of unpinned) {
    const date = new Date(session.last_activity);
    if (date >= today) {
      dateGroups[0].sessions.push(session);
    } else if (date >= yesterday) {
      dateGroups[1].sessions.push(session);
    } else if (date >= weekAgo) {
      dateGroups[2].sessions.push(session);
    } else {
      dateGroups[3].sessions.push(session);
    }
  }

  for (const g of dateGroups) {
    if (g.sessions.length > 0) groups.push(g);
  }

  return groups;
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

function SessionContextMenu({
  session,
  onRename,
  onTogglePin,
  onCopyLink,
  onDelete,
  onClose,
}: {
  session: ChatSessionSummary;
  onRename: () => void;
  onTogglePin: () => void;
  onCopyLink: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  const items = [
    {
      label: 'Rename',
      icon: <Pencil className="w-3.5 h-3.5" />,
      action: onRename,
    },
    {
      label: session.is_pinned ? 'Unpin' : 'Pin',
      icon: session.is_pinned ? (
        <PinOff className="w-3.5 h-3.5" />
      ) : (
        <Pin className="w-3.5 h-3.5" />
      ),
      action: onTogglePin,
    },
    {
      label: 'Copy Link',
      icon: <Link2 className="w-3.5 h-3.5" />,
      action: onCopyLink,
    },
    {
      label: 'Delete',
      icon: <Trash2 className="w-3.5 h-3.5" />,
      action: onDelete,
      danger: true,
    },
  ];

  return (
    <div
      ref={menuRef}
      className="absolute right-0 top-full mt-1 z-50 w-40 py-1 rounded-lg border border-white/10 bg-brand-midnight/95 backdrop-blur-sm shadow-xl"
    >
      {items.map((item) => (
        <button
          key={item.label}
          onClick={(e) => {
            e.stopPropagation();
            item.action();
          }}
          className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
            item.danger
              ? 'text-red-400 hover:bg-red-500/10'
              : 'text-brand-silver hover:bg-white/5 hover:text-white'
          }`}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function ChatHistorySidebar({
  activeSessionId,
  onSelectSession,
  onNewChat,
  refreshKey,
}: ChatHistorySidebarProps) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const didAutoSelect = useRef(false);
  const propsRef = useRef({ activeSessionId, onSelectSession });
  propsRef.current = { activeSessionId, onSelectSession };

  useEffect(() => {
    if (activeSessionId) {
      didAutoSelect.current = true;
    }
  }, [activeSessionId]);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await apiClient.get(
        `/ai/chat-sessions/?_t=${Date.now()}`
      );
      if (response.ok) {
        const data = await response.json();
        const list = Array.isArray(data) ? data : data.results ?? [];
        setSessions(list);

        if (
          !didAutoSelect.current &&
          !propsRef.current.activeSessionId &&
          list.length > 0
        ) {
          didAutoSelect.current = true;

          const savedSessionId =
            typeof window !== 'undefined'
              ? localStorage.getItem('active_chat_session')
              : null;
          const savedExists =
            savedSessionId &&
            list.some(
              (s: ChatSessionSummary) => s.session_id === savedSessionId
            );

          if (savedExists) {
            propsRef.current.onSelectSession(savedSessionId);
          } else {
            const sorted = [...list].sort(
              (a: ChatSessionSummary, b: ChatSessionSummary) =>
                new Date(b.last_activity).getTime() -
                new Date(a.last_activity).getTime()
            );
            propsRef.current.onSelectSession(sorted[0].session_id);
          }
        }
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

  // Focus rename input when entering rename mode
  useEffect(() => {
    if (renamingSessionId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingSessionId]);

  const executeDelete = async (sessionId: string) => {
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

  const handleDeleteFromMenu = (sessionId: string) => {
    setMenuOpenId(null);
    setDeleteConfirm(sessionId);
  };

  const handleRenameStart = (session: ChatSessionSummary) => {
    setRenamingSessionId(session.session_id);
    setRenameValue(session.title || '');
    setMenuOpenId(null);
  };

  const handleRenameSubmit = async (session: ChatSessionSummary) => {
    const trimmed = renameValue.trim();
    if (!trimmed || trimmed === session.title) {
      setRenamingSessionId(null);
      return;
    }
    try {
      const response = await apiClient.patch(
        `/ai/chat-sessions/${session.id}/`,
        { title: trimmed }
      );
      if (response.ok) {
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === session.session_id
              ? { ...s, title: trimmed }
              : s
          )
        );
      }
    } catch (err) {
      console.error('Failed to rename session:', err);
    }
    setRenamingSessionId(null);
  };

  const handleTogglePin = async (session: ChatSessionSummary) => {
    setMenuOpenId(null);
    // Optimistic update
    setSessions((prev) =>
      prev.map((s) =>
        s.session_id === session.session_id
          ? { ...s, is_pinned: !s.is_pinned }
          : s
      )
    );
    try {
      const response = await apiClient.post(
        `/ai/chat-sessions/${session.id}/toggle-pin/`,
        {}
      );
      if (!response.ok) {
        // Revert on failure
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === session.session_id
              ? { ...s, is_pinned: !s.is_pinned }
              : s
          )
        );
      }
    } catch {
      // Revert on error
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === session.session_id
            ? { ...s, is_pinned: !s.is_pinned }
            : s
        )
      );
    }
  };

  const handleCopyLink = (session: ChatSessionSummary) => {
    setMenuOpenId(null);
    const url = `${window.location.origin}/chat?session=${session.session_id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedSessionId(session.session_id);
      setTimeout(() => setCopiedSessionId(null), 2000);
    });
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
                const isRenaming = renamingSessionId === session.session_id;
                const isDeleteConfirm = deleteConfirm === session.session_id;
                const showCopied = copiedSessionId === session.session_id;

                return (
                  <div
                    key={session.session_id}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      if (!isRenaming) onSelectSession(session.session_id);
                    }}
                    onKeyDown={(e) => {
                      if (
                        !isRenaming &&
                        (e.key === 'Enter' || e.key === ' ')
                      ) {
                        e.preventDefault();
                        onSelectSession(session.session_id);
                      }
                    }}
                    onBlur={(e) => {
                      if (
                        isDeleteConfirm &&
                        !e.currentTarget.contains(e.relatedTarget as Node)
                      ) {
                        setTimeout(() => setDeleteConfirm(null), 200);
                      }
                    }}
                    className={`group relative w-full text-left px-2 py-2 rounded-lg mb-0.5 transition-colors cursor-pointer ${
                      isActive
                        ? 'bg-white/10 text-white'
                        : 'text-brand-silver hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 opacity-50" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          {isRenaming ? (
                            <input
                              ref={renameInputRef}
                              type="text"
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onKeyDown={(e) => {
                                e.stopPropagation();
                                if (e.key === 'Enter') {
                                  handleRenameSubmit(session);
                                } else if (e.key === 'Escape') {
                                  setRenamingSessionId(null);
                                }
                              }}
                              onBlur={() => handleRenameSubmit(session)}
                              onClick={(e) => e.stopPropagation()}
                              className="text-sm font-medium bg-white/5 border border-white/20 rounded px-1 py-0 w-full text-white outline-none focus:border-brand-electric/50"
                            />
                          ) : (
                            <span className="text-sm truncate font-medium flex items-center gap-1">
                              {session.is_pinned && (
                                <Pin className="w-3 h-3 shrink-0 text-brand-electric/60" />
                              )}
                              {session.title || 'Untitled'}
                            </span>
                          )}
                          <div className="relative shrink-0">
                            {isDeleteConfirm ? (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  executeDelete(session.session_id);
                                }}
                                className="p-0.5 rounded text-red-400 opacity-100 transition-colors"
                                title="Click again to confirm"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            ) : showCopied ? (
                              <span className="text-[10px] text-green-400 whitespace-nowrap">
                                <Check className="w-3 h-3 inline" /> Copied!
                              </span>
                            ) : (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setMenuOpenId(
                                    menuOpenId === session.session_id
                                      ? null
                                      : session.session_id
                                  );
                                  setDeleteConfirm(null);
                                }}
                                className="p-0.5 rounded text-brand-silver/30 opacity-0 group-hover:opacity-100 hover:text-white transition-colors"
                                title="More options"
                              >
                                <MoreHorizontal className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {menuOpenId === session.session_id && (
                              <SessionContextMenu
                                session={session}
                                onRename={() => handleRenameStart(session)}
                                onTogglePin={() => handleTogglePin(session)}
                                onCopyLink={() => handleCopyLink(session)}
                                onDelete={() =>
                                  handleDeleteFromMenu(session.session_id)
                                }
                                onClose={() => setMenuOpenId(null)}
                              />
                            )}
                          </div>
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
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
