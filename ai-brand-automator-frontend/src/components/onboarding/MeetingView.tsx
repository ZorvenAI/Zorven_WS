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
import { ArrowLeft } from 'lucide-react';

import AgentFeedbackStream, {
  type FeedbackItem,
} from '@/components/onboarding/AgentFeedbackStream';
import QuestionChecklist from '@/components/onboarding/QuestionChecklist';
import RightRail from '@/components/onboarding/RightRail';
import type { PreparedQuestion } from '@/lib/onboarding-sessions';

export interface MeetingViewProps {
  questions: PreparedQuestion[];
  version?: number | null;
  /** Placeholder in E-02; F-04 streams these in. */
  feedback?: FeedbackItem[];
  companyName?: string | null;
  /** Where "back" goes. Rendered inside this header — see the note below. */
  backHref?: string;
}

export default function MeetingView({
  questions,
  version,
  feedback = [],
  companyName,
  backHref,
}: MeetingViewProps) {
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
          <RightRail />
        </div>
      </div>
    </div>
  );
}
