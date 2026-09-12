'use client';

/**
 * The live meeting view (E-02, Design §11 MeetingView, FR-LIVE-02).
 *
 * "The horizontal split the requirement calls for: QuestionChecklist on top,
 * AgentFeedbackStream below, RightRail alongside."
 *
 * §11 also gives this component the WebSocket and the seq cursor. That is
 * F-04's work — E-02 is the shape, with placeholder data, so the stories that
 * fill it have somewhere to attach.
 *
 * One rule governs the whole file, quoted from §11: "nothing the agent
 * produces may steal focus. No modal, no toast that covers the checklist, no
 * auto-scroll that moves what the operator is reading." The operator is
 * conducting a conversation with a human being. Everything here is arranged
 * so that an arriving signal cannot interrupt them:
 *
 *   - no element in this tree ever calls .focus() or .scrollIntoView()
 *   - nothing is autoFocus'd
 *   - the feedback pane follows new items only while already at the bottom
 *   - the "N new" affordance sits inline under the feed, never over the
 *     checklist
 *
 * Building it now is cheaper than retrofitting it once G-02 through G-06 are
 * all pushing updates into the pane, which is what the card says too.
 */

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowLeft } from 'lucide-react';

import { useCaptureQueue } from '@/hooks/useCaptureQueue';
import { useLibraryPolling } from '@/hooks/useLibraryPolling';
import { useLiveSocket } from '@/hooks/useLiveSocket';
import { useTenantRole } from '@/hooks/useTenantRole';

import AgentFeedbackStream, {
  type FeedbackItem,
} from '@/components/onboarding/AgentFeedbackStream';
import QuestionChecklist from '@/components/onboarding/QuestionChecklist';
import RightRail from '@/components/onboarding/RightRail';
import ConsentModal from '@/components/onboarding/ConsentModal';
import type { CapturedMedia, ConsentDraft, ConsentState, PreparedQuestion } from '@/lib/onboarding-sessions';

function mergeCaptures(
  local: CapturedMedia[],
  server: CapturedMedia[],
): CapturedMedia[] {
  const seen = new Set(server.map((c) => c.id));
  const localOnly = local.filter((c) => !seen.has(c.id));
  return [...localOnly, ...server];
}

export interface MeetingViewProps {
  questions: PreparedQuestion[];
  version?: number | null;
  /** Placeholder in E-02; F-04 streams these in. */
  feedback?: FeedbackItem[];
  companyName?: string | null;
  /** Where "back" goes. Rendered inside this header — see the note below. */
  backHref?: string;
  /** F-01: null while it is still being read. */
  consent?: ConsentState | null;
  /** F-03: the recorder opens a MeetingRecording against this session. */
  sessionId?: string | null;
  onGrantConsent?: (draft: ConsentDraft) => Promise<void>;
}

export default function MeetingView({
  questions,
  version,
  feedback = [],
  companyName,
  backHref,
  consent = null,
  sessionId,
  onGrantConsent,
}: MeetingViewProps) {
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);

  const granted = consent?.granted === true;

  const confirmConsent = useCallback(
    async (draft: ConsentDraft) => {
      if (!onGrantConsent) return;
      setConsentSaving(true);
      setConsentError(null);
      try {
        await onGrantConsent(draft);
        setConsentOpen(false);
      } catch (error) {
        // Left open with the reason. Closing on failure would look like
        // success, and the operator would reach for a microphone that is
        // still shut.
        setConsentError(
          error instanceof Error ? error.message : 'Could not record consent.',
        );
      } finally {
        setConsentSaving(false);
      }
    },
    [onGrantConsent],
  );
  /**
   * Local only, and only for this story.
   *
   * The card is explicit: "Keep checkbox interactions in local state in this
   * story only. G-03 replaces that with server-authoritative state, and the
   * component boundary should already anticipate it." It does — QuestionChecklist
   * takes `checkedIds` and `onToggle` and does not care where they come from,
   * so G-03 swaps this useState for the server's answer and changes nothing
   * below.
   */
  const [checkedIds, setCheckedIds] = useState<ReadonlySet<string>>(new Set());

  const toggle = useCallback((questionId: string) => {
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(questionId)) {
        next.delete(questionId);
      } else {
        next.add(questionId);
      }
      return next;
    });
  }, []);

  const socket = useLiveSocket({
    sessionId: sessionId ?? null,
    enabled: granted,
  });

  const captureQueue = useCaptureQueue(sessionId ?? null);

  const library = useLibraryPolling(sessionId ?? null);
  const { isAdmin } = useTenantRole();

  return (
    /*
     * A fixed-height grid rather than a page that grows.
     *
     * AC-1 wants three regions "each scrolling without moving the others",
     * which is only true if the page itself does not scroll — otherwise the
     * outer scrollbar moves all three together and the panes are decorative.
     * min-h-0 on every track is what actually lets a flex/grid child shrink
     * below its content and hand the overflow to its own scroller; without it
     * children stay at content height and the page scrolls instead.
     */
    <div className="flex h-[calc(100vh-4rem)] min-h-0 flex-col gap-4 p-4">
      {/*
        AC-4: a revoked or absent consent is a blocking notice, not a subtle
        one. `consent === null` means "still reading" and shows nothing —
        flashing a compliance warning during a page load would train operators
        to dismiss it without reading.
      */}
      {consent !== null && !granted && (
        <div
          role="alert"
          className="shrink-0 rounded border border-amber-400/40 bg-amber-400/10 px-4 py-2 text-sm text-amber-200"
        >
          Recording is off: this meeting has no active consent. Record consent
          before opening the microphone.
        </div>
      )}

      {socket.status === 'degraded' && socket.error && (
        <div
          role="status"
          data-testid="degraded-banner"
          className="shrink-0 flex items-center gap-2 rounded border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          {socket.error.message}
        </div>
      )}

      <ConsentModal
        open={consentOpen}
        onCancel={() => setConsentOpen(false)}
        onConfirm={confirmConsent}
        saving={consentSaving}
        error={consentError}
      />

      {/*
        The back link lives here, not above this component.
        
        Stacked, it added a 28px row *outside* the fixed-height box, so the
        box started at y=92 while still being sized 100vh-4rem — and the page
        scrolled by exactly that 28px. AC-1's three independent scrollers are
        only independent while the document itself does not scroll; an outer
        scrollbar moves all three together. One header, one height.
      */}
      <header className="shrink-0">
        {backHref && (
          <Link
            href={backHref}
            className="mb-1 inline-flex items-center gap-2 text-sm text-brand-silver hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Session
          </Link>
        )}
        <h1 className="text-lg font-semibold text-white">
          Meeting{companyName ? ` · ${companyName}` : ''}
        </h1>
        <p className="text-sm text-brand-silver">
          Tick a question when it has been answered. The agent&rsquo;s
          suggestions appear below and never interrupt you.
        </p>
      </header>

      {/*
        Two columns on a laptop, one on narrow screens. `lg:` rather than `md:`
        because AC-2's target is a 13-inch laptop at typical zoom: at md the
        rail and the checklist share a width neither can use, and the question
        text starts wrapping every two or three words.
      */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* min-w-0 on the left track: without it a long unbroken question
            string sets the column's minimum width and the whole page scrolls
            sideways, which is exactly what AC-2 forbids. */}
        <div className="grid min-h-0 min-w-0 grid-rows-2 gap-4">
          <div data-testid="checklist-pane" className="min-h-0 overflow-y-auto">
            <QuestionChecklist
              questions={questions}
              version={version}
              checkedIds={checkedIds}
              onToggle={toggle}
            />
          </div>

          <AgentFeedbackStream items={feedback} />
        </div>

        <div className="min-h-0 min-w-0">
          <RightRail
            consentGranted={granted}
            sessionId={sessionId}
            onRecordConsent={() => setConsentOpen(true)}
            onCapture={captureQueue.enqueue}
            recordings={library.recordings}
            captures={mergeCaptures(captureQueue.captures, library.captures)}
            canDelete={isAdmin}
            onRecordingDeleted={library.refresh}
          />
        </div>
      </div>
    </div>
  );
}
