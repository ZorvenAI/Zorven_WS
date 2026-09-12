'use client';

/**
 * The lower pane of the meeting view (E-02, Design §11 AgentFeedbackStream).
 *
 * "Append-only feed of follow-up suggestions, notable facts, coverage changes
 * and gap warnings. Deliberately not a chat box — the operator is talking to a
 * person and cannot type. Everything here is glanceable in under two seconds."
 *
 * E-02 renders it with placeholder items; G-02 through G-06 supply real ones.
 * The scroll behaviour is built now rather than retrofitted, because by the
 * time four stories are pushing updates into this pane the wrong behaviour is
 * load-bearing.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Lightbulb, Sparkles, TrendingUp } from 'lucide-react';

export type FeedbackKind = 'follow_up' | 'fact' | 'coverage' | 'gap';

export interface FeedbackItem {
  id: string;
  kind: FeedbackKind;
  text: string;
  /** ISO-8601. Rendered in the viewer's zone. */
  at: string;
}

export interface AgentFeedbackStreamProps {
  items: FeedbackItem[];
}

const ICONS = {
  follow_up: Lightbulb,
  fact: Sparkles,
  coverage: TrendingUp,
  gap: AlertTriangle,
} as const;

const KIND_LABELS: Record<FeedbackKind, string> = {
  follow_up: 'Follow-up',
  fact: 'Noted',
  coverage: 'Coverage',
  gap: 'Gap',
};

const KIND_STYLES: Record<FeedbackKind, string> = {
  follow_up: 'text-brand-electric',
  fact: 'text-brand-silver',
  coverage: 'text-emerald-300',
  gap: 'text-amber-300',
};

/**
 * How close to the bottom still counts as "at the bottom".
 *
 * Not zero. Sub-pixel rounding and a partially visible last row mean an
 * operator who has scrolled all the way down often sits a pixel or two short,
 * and a strict comparison would decide they had scrolled away and then stop
 * following the stream for the rest of the meeting.
 */
const BOTTOM_THRESHOLD_PX = 24;

export default function AgentFeedbackStream({ items }: AgentFeedbackStreamProps) {
  const scroller = useRef<HTMLDivElement | null>(null);

  /**
   * Whether new items should pull the view down.
   *
   * True until the operator scrolls up, and true again the moment they return
   * to the bottom. §11's hard rule is that nothing the agent produces may
   * steal focus, and an unconditional scroll-to-bottom is the commonest way a
   * feed does exactly that: the operator is reading item four when item twenty
   * arrives and the text moves out from under them.
   */
  const [pinned, setPinned] = useState(true);
  const [unread, setUnread] = useState(0);
  const seen = useRef(items.length);

  const atBottom = useCallback((node: HTMLDivElement) => {
    return (
      node.scrollHeight - node.scrollTop - node.clientHeight <= BOTTOM_THRESHOLD_PX
    );
  }, []);

  const onScroll = useCallback(() => {
    const node = scroller.current;
    if (!node) return;
    const bottom = atBottom(node);
    setPinned(bottom);
    if (bottom) setUnread(0);
  }, [atBottom]);

  useEffect(() => {
    const node = scroller.current;
    const arrived = items.length - seen.current;
    seen.current = items.length;
    if (arrived <= 0 || !node) return;

    if (pinned) {
      // Assigning scrollTop rather than scrollIntoView: the latter can scroll
      // *ancestors* too, which moves the checklist in the pane above.
      node.scrollTop = node.scrollHeight;
    } else {
      // Counted, not shown to them by force. The affordance below lets the
      // operator choose the moment they catch up.
      setUnread((count) => count + arrived);
    }
  }, [items.length, pinned]);

  const jumpToLatest = useCallback(() => {
    const node = scroller.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
    setPinned(true);
    setUnread(0);
  }, []);

  return (
    <section
      aria-labelledby="feedback-heading"
      className="glass-card flex min-h-0 flex-col p-5"
    >
      <div className="flex items-center justify-between">
        <h2 id="feedback-heading" className="text-sm font-semibold text-white">
          Agent feedback
        </h2>
        <span className="text-xs text-brand-silver">{items.length} signals</span>
      </div>

      <div
        ref={scroller}
        onScroll={onScroll}
        data-testid="feedback-scroller"
        // AC-1: its own scroll container, so this pane moving leaves the
        // checklist and the rail exactly where they were.
        className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1"
        // Announced politely and never focused: an assertive region would
        // interrupt a screen-reader user mid-sentence, which is the audible
        // form of stealing focus.
        aria-live="polite"
        aria-relevant="additions"
      >
        {items.length === 0 ? (
          <p className="text-sm text-brand-silver">
            Suggestions, notable facts and coverage changes appear here once the
            meeting is running.
          </p>
        ) : (
          <ol className="space-y-2">
            {items.map((item) => {
              const Icon = ICONS[item.kind];
              return (
                // Keyed by id, never by index: a keyed-by-index list remounts
                // every row when one is prepended, and a remount is how an
                // input inside the tree would lose focus.
                <li key={item.id} className="flex items-start gap-2">
                  <Icon
                    aria-hidden="true"
                    className={`mt-0.5 h-4 w-4 shrink-0 ${KIND_STYLES[item.kind]}`}
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-white">
                      <span className={`mr-2 text-xs ${KIND_STYLES[item.kind]}`}>
                        {KIND_LABELS[item.kind]}
                      </span>
                      {item.text}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {unread > 0 && (
        // Inline and below the feed, not a toast over the checklist. §11: "no
        // toast that covers the checklist".
        <button
          type="button"
          onClick={jumpToLatest}
          className="mt-2 self-start text-xs text-brand-electric hover:underline"
        >
          {unread} new {unread === 1 ? 'signal' : 'signals'} — jump to latest
        </button>
      )}
    </section>
  );
}
