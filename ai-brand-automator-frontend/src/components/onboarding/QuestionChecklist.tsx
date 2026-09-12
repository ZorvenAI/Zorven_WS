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
  /**
   * Ids the operator has ticked (E-02).
   *
   * Only meaningful alongside `onToggle`. Held by the caller rather than here
   * so G-03 can replace local state with server-authoritative state without
   * touching this component — the boundary the E-02 card asks for.
   */
  checkedIds?: ReadonlySet<string>;
  /**
   * Omit for a read-only checklist, which is C-05's session page: the boxes
   * report the agent's sufficiency signal and must not move when clicked.
   * Supply it for the meeting view, where ticking one is the operator's job.
   *
   * Two modes rather than two components because the markup, the ordering
   * rule and the workflow tags are the same in both, and a fork would let
   * them drift — the numbering in particular, which the operator reads aloud.
   */
  onToggle?: (questionId: string) => void;
}

export default function QuestionChecklist({
  questions,
  version,
  checkedIds,
  onToggle,
}: QuestionChecklistProps) {
  const interactive = typeof onToggle === 'function';
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
              /*
               * E-02: `readOnly` belongs to the display mode only. An
               * interactive box is controlled by `checked` + `onChange` in the
               * ordinary way, and leaving `readOnly` on it would suppress the
               * very warning that tells you the handler is missing.
               */
              readOnly={!interactive}
              /*
               * Review was right that HTML ignores `readonly` on a checkbox,
               * and wrong about the remedy — and I checked before believing
               * either. A *controlled* checkbox is held by React: with
               * `checked` bound to server state and no onChange, React
               * restores the DOM after a click and the box does not move.
               * `readOnly` is there to suppress React's warning about
               * exactly that arrangement.
               *
               * Adding onClick={preventDefault} — the suggested fix — broke
               * it. Preventing the default interferes with React's own
               * restoration, and the box then really did toggle. The test
               * that clicks it caught that immediately, which is the whole
               * reason it clicks instead of reading an attribute.
               *
               * aria-disabled stays: the semantics were the sound half of the
               * finding. It says "this reflects a value, do not try to change
               * it" without `disabled` dropping the box out of the tab order
               * or announcing "unavailable" — G-03 makes these interactive
               * and the element should not change shape for that.
               */
              aria-disabled={interactive ? undefined : true}
              /*
               * Two sources of truth, deliberately not merged. In the display
               * mode the box reports the agent's sufficiency signal; in the
               * meeting it reports what the operator has ticked. G-03 is what
               * reconciles them, and doing it early here would bake in a
               * precedence rule that story has not decided yet.
               */
              checked={
                interactive
                  ? (checkedIds?.has(question.id) ?? false)
                  : question.status === 'GREEN'
              }
              onChange={interactive ? () => onToggle?.(question.id) : undefined}
              aria-label={question.text}
              className="mt-1 h-4 w-4 shrink-0 rounded border-white/20 bg-transparent"
            />
            <div className="min-w-0">
              {/*
                `break-words` is load-bearing, not decoration. Ordinary prose
                wraps on its own and so does a URL — browsers break after `/`,
                `?` and `&`. An unbroken run of characters does not, and
                operators paste those: a reference code, an API key, an order
                id. Without this the pane scrolls sideways, which is what AC-2
                forbids, and the document does not — so a page-level overflow
                check never sees it.
              */}
              <p className="break-words text-sm text-white">
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
