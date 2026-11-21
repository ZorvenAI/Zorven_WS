'use client';

import { lazy, Suspense, useState } from 'react';
import { CalendarDays, MessageSquare } from 'lucide-react';

import CalendarPane from '@/components/onboarding/CalendarPane';
import { useHasMounted } from '@/hooks/useHasMounted';
import { useTenantRole } from '@/hooks/useTenantRole';

const LazyChatInterface = lazy(() =>
  import('@/components/chat/ChatInterface').then((m) => ({
    default: () => m.ChatInterface({ defaultSidebarOpen: false, ignoreSessionParam: true }),
  })),
);

type SubTab = 'calendar' | 'chat';

export default function CalendarTab({ initialSubTab }: { initialSubTab?: SubTab }) {
  const { canEdit } = useTenantRole();
  const hasMounted = useHasMounted();
  const [activeSubTab, setActiveSubTab] = useState<SubTab>(initialSubTab ?? 'calendar');

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
        <div className="flex rounded-lg border border-white/10 p-0.5" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'calendar'}
            onClick={() => setActiveSubTab('calendar')}
            className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              activeSubTab === 'calendar'
                ? 'bg-white/10 text-white'
                : 'text-brand-silver hover:text-white'
            }`}
          >
            <CalendarDays className="h-3.5 w-3.5" aria-hidden />
            Calendar
          </button>
          {hasMounted && canEdit && (
            <button
              type="button"
              role="tab"
              aria-selected={activeSubTab === 'chat'}
              onClick={() => setActiveSubTab('chat')}
              className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                activeSubTab === 'chat'
                  ? 'bg-white/10 text-white'
                  : 'text-brand-silver hover:text-white'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" aria-hidden />
              Prepare in Chat
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeSubTab === 'calendar' && <CalendarPane />}
        <div className={activeSubTab === 'chat' ? 'h-full' : 'hidden'}>
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center bg-brand-midnight">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-electric/30 border-t-brand-electric" />
              </div>
            }
          >
            <LazyChatInterface />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
