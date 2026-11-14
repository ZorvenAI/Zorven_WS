'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ClipboardList,
  Loader2,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
} from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import {
  listSessions,
  type OnboardingSessionSummary,
  type SessionStatus,
} from '@/lib/onboarding-sessions';

const STATUS_STYLES: Record<SessionStatus, string> = {
  DRAFT: 'bg-slate-700/60 text-brand-silver',
  PREPARING: 'bg-amber-500/15 text-amber-300',
  READY: 'bg-emerald-500/15 text-emerald-300',
  MEETING_LIVE: 'bg-brand-electric/20 text-brand-electric',
  GATHERED: 'bg-teal-500/15 text-teal-300',
  PROCESSING: 'bg-sky-500/15 text-sky-300',
  REVIEW_PENDING: 'bg-violet-500/15 text-violet-300',
  CONFIRMED: 'bg-emerald-500/15 text-emerald-400',
  COMPLETED: 'bg-emerald-600/15 text-emerald-400',
  ESCALATED: 'bg-rose-500/15 text-rose-300',
  ARCHIVED: 'bg-slate-800/60 text-slate-400',
};

function StatusDot({ status }: { status: SessionStatus }) {
  const colorMap: Record<string, string> = {
    DRAFT: 'bg-slate-400',
    PREPARING: 'bg-amber-400',
    READY: 'bg-emerald-400',
    MEETING_LIVE: 'bg-brand-electric animate-pulse',
    GATHERED: 'bg-teal-400',
    PROCESSING: 'bg-sky-400 animate-pulse',
    REVIEW_PENDING: 'bg-violet-400',
    CONFIRMED: 'bg-emerald-500',
    COMPLETED: 'bg-emerald-500',
    ESCALATED: 'bg-rose-400',
    ARCHIVED: 'bg-slate-500',
  };
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${colorMap[status] ?? 'bg-slate-400'}`}
      title={status.replace('_', ' ').toLowerCase()}
    />
  );
}

function StatusChip({ status }: { status: SessionStatus }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium leading-tight ${
        STATUS_STYLES[status] ?? STATUS_STYLES.DRAFT
      }`}
    >
      {status.replace('_', ' ').toLowerCase()}
    </span>
  );
}

interface SessionListSidebarProps {
  selectedSessionId: string | null;
  onSelectSession: (session: OnboardingSessionSummary) => void;
  onSwitchToChat: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function SessionListSidebar({
  selectedSessionId,
  onSelectSession,
  onSwitchToChat,
  collapsed,
  onToggleCollapse,
}: SessionListSidebarProps) {
  const { canEdit: canEditRole } = useTenantRole();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => setHasMounted(true), []);
  const canEdit = hasMounted && canEditRole;

  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSessions(await listSessions());
    } catch (error) {
      setSessions([]);
      console.error('Failed to load onboarding sessions:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (collapsed) {
    return (
      <div className="flex w-12 shrink-0 flex-col items-center gap-3 border-r border-white/10 bg-white/[0.02] py-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded p-1 text-brand-silver hover:bg-white/10 hover:text-white"
          title="Expand session list"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
        <div className="mt-2 flex flex-col items-center gap-2">
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelectSession(s)}
              className={`rounded-full p-1 transition-colors ${
                selectedSessionId === s.id
                  ? 'bg-brand-electric/20 ring-1 ring-brand-electric/40'
                  : 'hover:bg-white/10'
              }`}
              title={s.company_name ?? s.company ?? 'Session'}
            >
              <StatusDot status={s.status} />
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-72 shrink-0 flex-col border-r border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-brand-electric" aria-hidden />
          <h2 className="text-sm font-semibold text-white">Sessions</h2>
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded p-1 text-brand-silver hover:bg-white/10 hover:text-white"
          title="Collapse session list"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-brand-silver">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : sessions.length === 0 ? (
          <div className="space-y-3 px-4 py-6">
            <p className="text-sm text-brand-silver">
              No onboarding sessions yet.
            </p>
            {canEdit && (
              <button
                type="button"
                onClick={onSwitchToChat}
                className="inline-flex items-center gap-2 text-sm text-brand-electric hover:underline"
              >
                <MessageSquare className="h-4 w-4" aria-hidden />
                Prepare your first meeting in chat
              </button>
            )}
          </div>
        ) : (
          <ul>
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => onSelectSession(session)}
                  className={`flex w-full items-start gap-3 border-b border-white/5 px-4 py-3 text-left transition-colors ${
                    selectedSessionId === session.id
                      ? 'bg-brand-electric/10 border-l-2 border-l-brand-electric'
                      : 'hover:bg-white/5'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-white">
                      {session.company_name ?? session.company ?? 'Unassigned company'}
                    </p>
                    <p className="mt-0.5 text-[11px] text-brand-silver">
                      {new Date(session.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                  <StatusChip status={session.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {canEdit && sessions.length > 0 && (
        <div className="border-t border-white/10 px-4 py-3">
          <button
            type="button"
            onClick={onSwitchToChat}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
          >
            <Plus className="h-3.5 w-3.5" />
            New Session
          </button>
        </div>
      )}
    </div>
  );
}
