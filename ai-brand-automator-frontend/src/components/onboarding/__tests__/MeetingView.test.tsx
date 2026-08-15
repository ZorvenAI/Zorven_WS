/**
 * E-02 · the meeting view's layout and its focus rules.
 *
 * The card names `test_focus_preserved_on_stream_update` and
 * `test_no_autoscroll_after_manual_scroll`. FR-LIVE-02 is more specific about
 * the first: "asserted by a frontend test that types continuously while
 * signals stream in", which is what `types continuously` below does — a
 * keystroke, a signal, a keystroke, for the length of a sentence.
 *
 * What jsdom can and cannot do here is worth stating, because a test that
 * quietly proves nothing is worse than an absent one. jsdom has no layout
 * engine: every element reports zero width and height, and `scrollTop`
 * assignments are stored rather than clamped. So the scroll tests below drive
 * the arithmetic by setting scrollHeight/clientHeight/scrollTop explicitly —
 * which does exercise the real component logic — while AC-2, a claim about
 * how the layout behaves at a real viewport, is covered by the Playwright
 * spec in e2e/meeting-view.spec.ts and cannot be covered here.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import AgentFeedbackStream, {
  type FeedbackItem,
} from '@/components/onboarding/AgentFeedbackStream';
import MeetingView from '@/components/onboarding/MeetingView';
import type { PreparedQuestion } from '@/lib/onboarding-sessions';

function aQuestion(n: number): PreparedQuestion {
  // Every field the type declares, not a cast past the ones that were
  // inconvenient. `as PreparedQuestion` over a partial object compiles until
  // the interface grows, and then keeps compiling while the fixture drifts
  // away from what the server actually sends.
  return {
    id: `q-${n}`,
    order: n,
    text: `Question number ${n} about the brand and how it came to be`,
    origin: 'PREPARED',
    workflow_target: n % 3 === 0 ? 'WF3' : n % 2 === 0 ? 'WF2' : 'WF1',
    target_field: `field_${n}`,
    status: 'OPEN',
  };
}

const QUESTIONS = Array.from({ length: 20 }, (_, i) => aQuestion(i + 1));

function aSignal(n: number): FeedbackItem {
  return {
    id: `f-${n}`,
    kind: 'follow_up',
    text: `Signal number ${n}`,
    at: '2026-08-13T10:00:00Z',
  };
}

/**
 * Gives a scroll container the geometry jsdom will not compute, so the
 * component's own pinned/unpinned arithmetic runs against real numbers.
 */
function giveGeometry(
  node: HTMLElement,
  { scrollHeight, clientHeight }: { scrollHeight: number; clientHeight: number },
) {
  Object.defineProperty(node, 'scrollHeight', {
    configurable: true,
    get: () => scrollHeight,
  });
  Object.defineProperty(node, 'clientHeight', {
    configurable: true,
    get: () => clientHeight,
  });
}

/** A stream whose items can be appended from outside, as F-04 will append them. */
function StreamHarness({ initial = 1 }: { initial?: number }) {
  const [items, setItems] = useState<FeedbackItem[]>(
    Array.from({ length: initial }, (_, i) => aSignal(i + 1)),
  );
  return (
    <>
      <button
        type="button"
        onClick={() => setItems((prior) => [...prior, aSignal(prior.length + 1)])}
      >
        emit signal
      </button>
      <label htmlFor="note">Note</label>
      <input id="note" />
      <AgentFeedbackStream items={items} />
    </>
  );
}

describe('MeetingView layout (AC-1)', () => {
  it('renders the three regions', () => {
    render(<MeetingView questions={QUESTIONS} version={3} />);

    expect(
      screen.getByRole('region', { name: /prepared questions/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: /agent feedback/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('complementary', { name: /recordings and captures/i }),
    ).toBeInTheDocument();
  });

  it('gives each region its own scroll container', () => {
    /**
     * The structural half of AC-1: three separate overflow containers rather
     * than one page scroller. If the panes shared the page's scrollbar they
     * would move together, and "each scrolling without moving the others"
     * would be false however it looked.
     */
    const { container } = render(<MeetingView questions={QUESTIONS} />);

    for (const id of ['checklist-pane', 'feedback-scroller', 'rail-scroller']) {
      expect(screen.getByTestId(id).className).toContain('overflow-y-auto');
    }
    // And the page itself does not scroll: the outer shell is a fixed-height
    // flex column, so the overflow belongs to the panes.
    expect(container.firstElementChild?.className).toContain('h-[calc(100vh-4rem)]');
  });

  it('keeps the capture controls reachable above the rail list', () => {
    /** FR-LIVE-02: "capture and recording controls always reachable". They sit
     *  outside the rail's scroller, so a long list cannot push them away. */
    render(<MeetingView questions={QUESTIONS} />);

    const rail = screen.getByRole('complementary', { name: /recordings/i });
    const record = within(rail).getByRole('button', { name: /start recording/i });

    expect(screen.getByTestId('rail-scroller').contains(record)).toBe(false);
  });
});

describe('checkbox state (E-02 local only)', () => {
  it('ticks and unticks a question', async () => {
    const user = userEvent.setup();
    render(<MeetingView questions={QUESTIONS.slice(0, 3)} />);

    const box = screen.getByRole('checkbox', { name: QUESTIONS[0].text });
    expect(box).not.toBeChecked();

    await user.click(box);
    expect(box).toBeChecked();

    await user.click(box);
    expect(box).not.toBeChecked();
  });

  it('leaves the read-only checklist read-only', async () => {
    /**
     * The control for the two-mode props. C-05's session page renders the same
     * component without `onToggle`, where a box reports the agent's signal and
     * must not move when clicked — the behaviour #566 was opened to protect.
     */
    const user = userEvent.setup();
    const QuestionChecklist = (
      await import('@/components/onboarding/QuestionChecklist')
    ).default;
    render(<QuestionChecklist questions={QUESTIONS.slice(0, 2)} version={1} />);

    const box = screen.getByRole('checkbox', { name: QUESTIONS[0].text });
    await user.click(box);

    expect(box).not.toBeChecked();
    expect(box).toHaveAttribute('aria-disabled', 'true');
  });
});

/** MeetingView with feedback that can be appended from outside, as F-04 will. */
function MeetingHarness() {
  const [feedback, setFeedback] = useState<FeedbackItem[]>([aSignal(1)]);
  return (
    <>
      <button
        type="button"
        onClick={() => setFeedback((prior) => [...prior, aSignal(prior.length + 1)])}
      >
        emit signal
      </button>
      <MeetingView questions={QUESTIONS} feedback={feedback} />
    </>
  );
}

describe('AC-3 · nothing steals focus', () => {
  it('keeps focus on a checkbox while signals arrive', () => {
    /**
     * AC-3's own wording is "the operator ... interacting with a checkbox",
     * and this is the case the sibling-input test cannot reach: the checkbox
     * lives *inside* the tree that re-renders when feedback arrives, so a
     * remount of the checklist — a conditional wrapper, a key tied to
     * something that changes — would drop focus on the floor.
     */
    render(<MeetingHarness />);

    const box = screen.getByRole('checkbox', { name: QUESTIONS[4].text });
    box.focus();
    expect(document.activeElement).toBe(box);

    const emit = screen.getByRole('button', { name: /emit signal/i });
    for (let i = 0; i < 5; i += 1) fireEvent.click(emit);

    expect(document.activeElement).toBe(box);
  });

  it('keeps a half-typed note intact through a burst of signals', () => {
    /**
     * The same hazard for text: a remount restores an empty input, and the
     * operator's half-written sentence is gone. Bursts rather than one signal,
     * because G-02 through G-06 will push several at once.
     */
    render(<StreamHarness />);
    const note = screen.getByLabelText('Note') as HTMLInputElement;
    fireEvent.change(note, { target: { value: 'small batch roas' } });
    note.focus();

    const emit = screen.getByRole('button', { name: /emit signal/i });
    for (let i = 0; i < 8; i += 1) fireEvent.click(emit);

    expect(document.activeElement).toBe(note);
    expect(note.value).toBe('small batch roas');
  });

  it('test_focus_preserved_on_stream_update', async () => {
    /**
     * FR-LIVE-02's own wording: a test that "types continuously while signals
     * stream in". Typed one character at a time with a signal arriving between
     * every keystroke, then the three things a stolen focus would break —
     * which element has it, what it contains, and where the caret sits.
     */
    const user = userEvent.setup();
    render(<StreamHarness />);

    const note = screen.getByLabelText('Note') as HTMLInputElement;
    const emit = screen.getByRole('button', { name: /emit signal/i });
    await user.click(note);

    const sentence = 'they roast in small batches';
    for (const character of sentence) {
      await user.type(note, character);
      fireEvent.click(emit);
    }

    expect(document.activeElement).toBe(note);
    expect(note.value).toBe(sentence);
    expect(note.selectionStart).toBe(sentence.length);
  });

  it('test_no_autoscroll_after_manual_scroll', () => {
    /**
     * The operator has scrolled up to read something. New signals must not
     * drag the view back down — §11: "no auto-scroll that moves what the
     * operator is reading".
     */
    const { rerender } = render(
      <AgentFeedbackStream items={[aSignal(1), aSignal(2)]} />,
    );
    const scroller = screen.getByTestId('feedback-scroller');
    giveGeometry(scroller, { scrollHeight: 1000, clientHeight: 200 });

    // Scrolled well away from the bottom, and the component told about it.
    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);

    rerender(<AgentFeedbackStream items={[aSignal(1), aSignal(2), aSignal(3)]} />);

    expect(scroller.scrollTop).toBe(100);
    // Counted instead, so the operator can catch up on their own terms.
    expect(
      screen.getByRole('button', { name: /1 new signal/i }),
    ).toBeInTheDocument();
  });

  it('follows the stream while the operator is already at the bottom', () => {
    /**
     * The control. A pane that never scrolled would pass the test above and
     * force the operator to scroll manually for the whole meeting.
     */
    const { rerender } = render(<AgentFeedbackStream items={[aSignal(1)]} />);
    const scroller = screen.getByTestId('feedback-scroller');
    giveGeometry(scroller, { scrollHeight: 1000, clientHeight: 200 });

    scroller.scrollTop = 800; // exactly at the bottom
    fireEvent.scroll(scroller);

    rerender(<AgentFeedbackStream items={[aSignal(1), aSignal(2)]} />);

    expect(scroller.scrollTop).toBe(1000);
    expect(screen.queryByRole('button', { name: /new signal/i })).toBeNull();
  });

  it('resumes following once the operator scrolls back down', () => {
    const { rerender } = render(<AgentFeedbackStream items={[aSignal(1)]} />);
    const scroller = screen.getByTestId('feedback-scroller');
    giveGeometry(scroller, { scrollHeight: 1000, clientHeight: 200 });

    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);
    rerender(<AgentFeedbackStream items={[aSignal(1), aSignal(2)]} />);
    expect(scroller.scrollTop).toBe(100);

    scroller.scrollTop = 800;
    fireEvent.scroll(scroller);
    rerender(<AgentFeedbackStream items={[aSignal(1), aSignal(2), aSignal(3)]} />);

    expect(scroller.scrollTop).toBe(1000);
  });

  it.each([
    ['exactly at the bottom', 800, true],
    ['within the rounding threshold', 790, true],
    ['a clear scroll away', 700, false],
  ])('%s → follows: %j', (_label, scrollTop, shouldFollow) => {
    /**
     * The boundary is not zero on purpose: sub-pixel rounding and a partly
     * visible last row leave an operator who has scrolled all the way down
     * sitting a pixel or two short, and a strict comparison would decide they
     * had scrolled away and stop following for the rest of the meeting.
     */
    const { rerender } = render(<AgentFeedbackStream items={[aSignal(1)]} />);
    const scroller = screen.getByTestId('feedback-scroller');
    giveGeometry(scroller, { scrollHeight: 1000, clientHeight: 200 });

    scroller.scrollTop = scrollTop;
    fireEvent.scroll(scroller);
    rerender(<AgentFeedbackStream items={[aSignal(1), aSignal(2)]} />);

    expect(scroller.scrollTop).toBe(shouldFollow ? 1000 : scrollTop);
  });

  it('puts the catch-up affordance below the feed, never over the checklist', () => {
    /** §11: "no modal, no toast that covers the checklist." */
    render(<MeetingView questions={QUESTIONS} feedback={[aSignal(1)]} />);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    // Politely announced, so a screen reader is not interrupted mid-sentence.
    expect(screen.getByTestId('feedback-scroller')).toHaveAttribute(
      'aria-live',
      'polite',
    );
  });
});

// ── F-01 · consent gates the microphone ──────────────────────────────

const NO_CONSENT = {
  granted: false,
  granted_at: null,
  method: null,
  scope: null,
} as const;

const GRANTED = {
  granted: true,
  granted_at: '2026-08-14T10:00:00Z',
  method: 'VERBAL_RECORDED',
  scope: { audio: true, transcript: true, captured_media: true },
} as const;

describe('F-01 · consent before the microphone', () => {
  it('shows the record control disabled, with the reason stated inline', () => {
    /**
     * AC-1 is specific that this must not be "an unexplained grey button".
     * The reason is asserted as visible text, not as a title attribute — a
     * tooltip is invisible to touch and to most screen readers, so it is not
     * a stated reason.
     */
    render(<MeetingView questions={QUESTIONS} consent={NO_CONSENT} />);

    const record = screen.getByRole('button', { name: /start recording/i });
    expect(record).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Record consent to enable recording')).toBeInTheDocument();
  });

  it('opens the consent modal when the disabled control is clicked', async () => {
    /**
     * AC-1's second half: "clicking it opens the consent modal rather than
     * doing nothing". This is why the control carries aria-disabled instead of
     * `disabled` — a truly disabled button cannot be clicked at all, so the
     * criterion would be unsatisfiable.
     */
    const user = userEvent.setup();
    render(<MeetingView questions={QUESTIONS} consent={NO_CONSENT} />);

    await user.click(screen.getByRole('button', { name: /start recording/i }));

    expect(screen.getByRole('dialog', { name: /record consent/i })).toBeInTheDocument();
  });

  it('blocks the view with a notice while consent is missing', () => {
    render(<MeetingView questions={QUESTIONS} consent={NO_CONSENT} />);

    expect(screen.getByRole('alert')).toHaveTextContent(/no active consent/i);
  });

  it('shows no notice and no reason once consent is granted', () => {
    /** The control. A banner that never cleared would make AC-4's revocation
     *  notice meaningless — an always-on warning is wallpaper. */
    render(<MeetingView questions={QUESTIONS} consent={GRANTED} />);

    expect(screen.queryByRole('alert')).toBeNull();
    expect(
      screen.queryByText('Record consent to enable recording'),
    ).not.toBeInTheDocument();
  });

  it('says nothing at all while consent is still being read', () => {
    /**
     * `null` is "not yet known", not "absent". Flashing a compliance warning
     * during a page load is how operators learn to dismiss them unread.
     */
    render(<MeetingView questions={QUESTIONS} consent={null} />);

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('sends the name, method and full scope, and closes on success', async () => {
    const user = userEvent.setup();
    const granted: unknown[] = [];
    render(
      <MeetingView
        questions={QUESTIONS}
        consent={NO_CONSENT}
        onGrantConsent={async (draft) => {
          granted.push(draft);
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /start recording/i }));
    await user.type(screen.getByLabelText(/who is consenting/i), 'Asha Kalyani');
    await user.click(screen.getByRole('button', { name: /^record consent$/i }));

    expect(granted).toEqual([
      {
        subject_name: 'Asha Kalyani',
        method: 'VERBAL_RECORDED',
        // The scope the sentence above the button describes. If these drift,
        // the operator has confirmed something other than what was recorded.
        scope: { audio: true, transcript: true, captured_media: true },
      },
    ]);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps the modal open, with the reason, when recording consent fails', async () => {
    /** Closing on failure would look like success, and the operator would
     *  reach for a microphone that is still shut. */
    const user = userEvent.setup();
    render(
      <MeetingView
        questions={QUESTIONS}
        consent={NO_CONSENT}
        onGrantConsent={async () => {
          throw new Error('API 502: upstream unavailable');
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /start recording/i }));
    await user.type(screen.getByLabelText(/who is consenting/i), 'Asha Kalyani');
    await user.click(screen.getByRole('button', { name: /^record consent$/i }));

    // Scoped to the dialog: the blocking banner behind it is also an alert,
    // so an unscoped query is ambiguous — and would pass on the banner even
    // if the modal showed no reason at all.
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/502/);
  });

  it('AC-4 · a revocation puts the notice back and disables the control', () => {
    /**
     * Driven as a prop change, which is what the page's poll produces when
     * someone revokes from the session detail page. The card calls the
     * revocation path "the part teams skip".
     */
    const { rerender } = render(
      <MeetingView questions={QUESTIONS} consent={GRANTED} />,
    );
    expect(screen.queryByRole('alert')).toBeNull();

    rerender(<MeetingView questions={QUESTIONS} consent={NO_CONSENT} />);

    expect(screen.getByRole('alert')).toHaveTextContent(/no active consent/i);
    expect(screen.getByRole('button', { name: /start recording/i })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
});
