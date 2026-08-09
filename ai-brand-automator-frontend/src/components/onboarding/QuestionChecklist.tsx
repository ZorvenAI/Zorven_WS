'use client';

/**
 * QuestionChecklist — the approved questions, ready for the meeting (C-05).
 *
 * Design §11 places this inside MeetingView, where G-03 will tick boxes from
 * the agent's sufficiency signals. C-05 renders the same component in the
 * Onboarding Interface so the operator sees the set before the meeting starts.
 * One component, two homes — which is why the card is firm that checkbox state
 * stays server-authoritative: "a component built around local state has to be
 * rewritten" once the signals arrive.
 *
 * So there is no local state here at all. A question is ticked because the
 * server says GREEN, and nothing in this component can change that. The toggle
 * belongs to G-03, along with the endpoint to record an operator's override —
 * which §11 notes is "a training signal, not just UI state" and therefore
 * cannot be a checkbox that only the browser knows about.
 *
 * That also settles AC-3 by construction: re-approval replaces the rendered
 * set wholesale, so there is no per-question client state for a question that
 * no longer exists to survive in.
 */

import Link from 'next/link';
import { MessageSquare } from 'lucide-react';

import type { PreparedQuestion, WorkflowTarget } from '@/lib/onboarding-sessions';

/**
 * Quiet on purpose. The card: workflow tags "matter to the operator's sense of
 * coverage but they must not compete with the question text during a live
 * conversation." So they are small, low-contrast, and not part of the row's
 * accessible name.
 */
const TAG_STYLES: Record<WorkflowTarget, string> = {
  WF1: 'text-sky-300/70',
  WF2: 'text-violet-300/70',
  WF3: 'text-amber-300/70',
};

const TAG_LABELS: Record<WorkflowTarget, string> = {
  WF1: 'discovery',
  WF2: 'strategy',
  WF3: 'campaigns',
};

export interface QuestionChecklistProps {
  questions: PreparedQuestion[];
  /** Null when the session has no approved questionnaire yet (AC-2). */
  version?: number | null;
}

export default function QuestionChecklist({
  questions,
  version,
}: QuestionChecklistProps) {
  if (questions.length === 0) {
    return (
      <section aria-labelledby="checklist-heading" className="glass-card p-5">
        <h2 id="checklist-heading" className="text-sm font-semibold text-white">
          Prepared questions
        </h2>
        {/*
          AC-2: "an empty state linking directly into the chat prep flow,
          rather than an empty box". A dead end here is an operator who has to
          work out on their own where preparation happens.
        */}
        <p className="mt-3 text-sm text-brand-silver">
          No approved questionnaire for this session yet. Questions you prepare
          and approve in chat appear here, ready for the meeting.
        </p>
        <Link
          href="/chat"
          className="mt-3 inline-flex items-center gap-2 text-sm text-brand-electric hover:underline"
        >
          <MessageSquare className="h-4 w-4" aria-hidden />
          Prepare questions in chat
        </Link>
      </section>
    );
  }

  return (
    <section aria-labelledby="checklist-heading" className="glass-card p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="checklist-heading" className="text-sm font-semibold text-white">
          Prepared questions
        </h2>
        {version != null && (
          <span className="text-xs text-brand-silver">version {version}</span>
        )}
      </div>

      <ol className="mt-3 space-y-2">
        {/*
          Rendered in the order the server sent, which C-04 renumbers to be
          contiguous after every edit. Sorting here would let the component and
          the approved record disagree about what "question 4" means, and the
          operator says that number out loud.
        */}
        {questions.map((question, index) => (
          <li key={question.id} className="flex items-start gap-3">
            <input
              type="checkbox"
              readOnly
              checked={question.status === 'GREEN'}
              aria-label={question.text}
              className="mt-1 h-4 w-4 shrink-0 rounded border-white/20 bg-transparent"
            />
            <div className="min-w-0">
              <p className="text-sm text-white">
                <span className="mr-2 text-brand-silver">{index + 1}.</span>
                {question.text}
              </p>
              <span
                className={`text-xs ${TAG_STYLES[question.workflow_target]}`}
                // Not part of the accessible name: a screen reader announcing
                // "campaigns" before every question would be the audible
                // version of a tag competing with the text.
                aria-hidden
              >
                {TAG_LABELS[question.workflow_target]}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
