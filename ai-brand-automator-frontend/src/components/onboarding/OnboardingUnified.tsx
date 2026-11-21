'use client';

/**
 * OnboardingUnified — single-screen OIA interface.
 *
 * Replaces the three-page flow (OnboardingHome → SessionDetail → Meeting/Review)
 * with a master-detail layout: session list on the left, tabbed detail on the right.
 *
 * The 5-step wizard forms (step-1 through step-5) are untouched and linked
 * from the header.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  CalendarDays,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  Radio,
} from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import SessionListSidebar from '@/components/onboarding/SessionListSidebar';
import SessionOverviewTab from '@/components/onboarding/SessionOverviewTab';
import MeetingTab from '@/components/onboarding/MeetingTab';
import KeyFindingsReview from '@/components/onboarding/KeyFindingsReview';
import CalendarTab from '@/components/onboarding/CalendarTab';
import DescriptionTab from '@/components/onboarding/DescriptionTab';
import {
  wizardDeepLink,
  type OnboardingSessionSummary,
} from '@/lib/onboarding-sessions';

type DetailTab = 'overview' | 'meeting' | 'review' | 'description' | 'calendar';

function isValidTab(value: string | null): value is DetailTab {
  return value === 'overview' || value === 'meeting' || value === 'review' || value === 'description' || value === 'calendar';
}

function Inner({
  initialSessionId,
  initialTab,
}: {
  initialSessionId: string | null;
  initialTab: DetailTab;
}) {
  const router = useRouter();
  const { canEdit: canEditRole } = useTenantRole();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => { setHasMounted(true); }, []);
  const canEdit = hasMounted && canEditRole;

  const [selectedSession, setSelectedSession] =
    useState<OnboardingSessionSummary | null>(() =>
      initialSessionId
        ? {
            id: initialSessionId,
            company: null,
            company_name: null,
            status: 'DRAFT' as const,
            questionnaire: null,
            created_at: '',
            updated_at: '',
          }
        : null,
    );
  const [activeTab, setActiveTab] = useState<DetailTab>(initialTab);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const updateUrl = useCallback(
    (sessionId: string | null, tab: DetailTab) => {
      const params = new URLSearchParams();
      if (sessionId) params.set('session', sessionId);
      params.set('tab', tab);
      const query = params.toString();
      router.replace(`/onboarding?${query}`, { scroll: false });
    },
    [router],
  );

  const handleSelectSession = useCallback(
    (session: OnboardingSessionSummary) => {
      setSelectedSession(session);
      const tab = activeTab === 'calendar' ? 'overview' : activeTab;
      setActiveTab(tab);
      updateUrl(session.id, tab);
    },
    [activeTab, updateUrl],
  );

  const handleTabChange = useCallback(
    (tab: DetailTab) => {
      setActiveTab(tab);
      updateUrl(selectedSession?.id ?? null, tab);
    },
    [selectedSession, updateUrl],
  );

  const handleSwitchToChat = useCallback(() => {
    setActiveTab('calendar');
    updateUrl(null, 'calendar');
  }, [updateUrl]);

  const showOverviewTab = !!selectedSession;
  const showMeetingTab =
    !!selectedSession &&
    (selectedSession.status === 'READY' ||
      selectedSession.status === 'MEETING_LIVE' ||
      selectedSession.status === 'GATHERED' ||
      activeTab === 'meeting');
  const showReviewTab =
    !!selectedSession &&
    (selectedSession.status === 'REVIEW_PENDING' ||
      selectedSession.status === 'CONFIRMED' ||
      selectedSession.status === 'COMPLETED' ||
      activeTab === 'review');
  const showDescriptionTab =
    !!selectedSession &&
    (selectedSession.status === 'REVIEW_PENDING' ||
      selectedSession.status === 'CONFIRMED' ||
      selectedSession.status === 'COMPLETED' ||
      activeTab === 'description');

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2">
        <div>
          <h1 className="text-lg font-semibold text-white">Onboarding</h1>
          <p className="text-xs text-brand-silver">
            Prepare, meet, review — all in one place.
          </p>
        </div>
        <Link
          href={wizardDeepLink(selectedSession)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
        >
          <FileText className="h-3.5 w-3.5" aria-hidden />
          Go to Forms
        </Link>
      </header>

      {/* Main content: sidebar + detail */}
      <div className="flex min-h-0 flex-1">
        <SessionListSidebar
          selectedSessionId={selectedSession?.id ?? null}
          onSelectSession={handleSelectSession}
          onSwitchToChat={handleSwitchToChat}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        />

        {/* Detail panel */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* Tab bar */}
          {selectedSession && (
            <div className="flex shrink-0 items-center gap-1 border-b border-white/10 px-4 py-1.5">
              <TabButton
                icon={<LayoutDashboard className="h-3.5 w-3.5" />}
                label="Overview"
                active={activeTab === 'overview'}
                visible={showOverviewTab}
                onClick={() => handleTabChange('overview')}
              />
              <TabButton
                icon={<Radio className="h-3.5 w-3.5" />}
                label="Meeting"
                active={activeTab === 'meeting'}
                visible={showMeetingTab}
                onClick={() => handleTabChange('meeting')}
              />
              <TabButton
                icon={<ClipboardCheck className="h-3.5 w-3.5" />}
                label="Review"
                active={activeTab === 'review'}
                visible={showReviewTab}
                onClick={() => handleTabChange('review')}
              />
              <TabButton
                icon={<FileText className="h-3.5 w-3.5" />}
                label="Description"
                active={activeTab === 'description'}
                visible={showDescriptionTab}
                onClick={() => handleTabChange('description')}
              />
              <div className="mx-2 h-4 w-px bg-white/10" />
              <TabButton
                icon={<CalendarDays className="h-3.5 w-3.5" />}
                label="Calendar"
                active={activeTab === 'calendar'}
                visible
                onClick={() => handleTabChange('calendar')}
              />
            </div>
          )}

          {/* Tab content */}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {activeTab === 'overview' && selectedSession && (
              <SessionOverviewTab
                sessionId={selectedSession.id}
                onOpenMeeting={() => handleTabChange('meeting')}
                onOpenReview={() => handleTabChange('review')}
              />
            )}
            {activeTab === 'meeting' && selectedSession && (
              <MeetingTab
                sessionId={selectedSession.id}
                onBack={() => handleTabChange('overview')}
              />
            )}
            {activeTab === 'review' && selectedSession && (
              <KeyFindingsReview sessionId={selectedSession.id} />
            )}
            {activeTab === 'description' && selectedSession && (
              <DescriptionTab sessionId={selectedSession.id} />
            )}
            {activeTab === 'calendar' && <CalendarTab />}
            {!selectedSession && activeTab !== 'calendar' && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-brand-silver">
                <LayoutDashboard className="h-10 w-10 opacity-30" />
                <p className="text-sm">Select a session to get started</p>
                {canEdit && (
                  <button
                    type="button"
                    onClick={handleSwitchToChat}
                    className="text-sm text-brand-electric hover:underline"
                  >
                    or prepare a new one in chat
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TabButton({
  icon,
  label,
  active,
  visible,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  visible: boolean;
  onClick: () => void;
}) {
  if (!visible) return null;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'bg-white/10 text-white'
          : 'text-brand-silver hover:bg-white/5 hover:text-white'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

export default function OnboardingUnified() {
  const searchParams = useSearchParams();
  const sessionParam = searchParams?.get('session') ?? null;
  const tabParam = searchParams?.get('tab') ?? null;
  const tab: DetailTab = isValidTab(tabParam) ? tabParam : sessionParam ? 'overview' : 'calendar';

  return <Inner initialSessionId={sessionParam} initialTab={tab} />;
}
