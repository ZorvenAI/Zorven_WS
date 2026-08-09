/**
 * C-05 · the prepared-question checklist.
 *
 * The card names two cases here — `test_renders_approved_set` and
 * `test_empty_state_links_to_prep`.
 */

import { render, screen, within } from '@testing-library/react';

import QuestionChecklist from '@/components/onboarding/QuestionChecklist';
import type { PreparedQuestion } from '@/lib/onboarding-sessions';

function question(overrides: Partial<PreparedQuestion> = {}): PreparedQuestion {
  return {
    id: 'q-1',
    order: 0,
    text: 'What do you sell?',
    origin: 'PREPARED',
    workflow_target: 'WF1',
    target_field: '',
    status: 'OPEN',
    ...overrides,
  };
}

const APPROVED_SET: PreparedQuestion[] = [
  question({ id: 'q-1', order: 0, text: 'What do you sell?', workflow_target: 'WF1' }),
  question({
    id: 'q-2',
    order: 1,
    text: 'What makes you different?',
    workflow_target: 'WF2',
  }),
  question({
    id: 'q-3',
    order: 2,
    text: 'Do you have previous ads we could reuse?',
    workflow_target: 'WF3',
  }),
];

describe('QuestionChecklist', () => {
  it('test_renders_approved_set', () => {
    /** The card's named case: order and tags correct. */
    render(<QuestionChecklist questions={APPROVED_SET} version={2} />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);

    // In the server's order, not sorted here. The operator says "question 4"
    // out loud, and the component and the approved record have to agree.
    expect(items[0]).toHaveTextContent('What do you sell?');
    expect(items[2]).toHaveTextContent('Do you have previous ads we could reuse?');

    expect(items[0]).toHaveTextContent('discovery');
    expect(items[1]).toHaveTextContent('strategy');
    expect(items[2]).toHaveTextContent('campaigns');

    expect(screen.getByText('version 2')).toBeInTheDocument();
  });

  it('renders every box unchecked when nothing has been answered', () => {
    render(<QuestionChecklist questions={APPROVED_SET} />);

    for (const box of screen.getAllByRole('checkbox')) {
      expect(box).not.toBeChecked();
    }
  });

  it('ticks a box because the server says GREEN, not because of a click', () => {
    /**
     * Checkbox state is server-authoritative — G-03 drives it from sufficiency
     * signals, and the card warns that a component built around local state
     * has to be rewritten. Rendering from `status` is what makes that true.
     */
    render(
      <QuestionChecklist
        questions={[question({ id: 'q-1', status: 'GREEN' }), question({ id: 'q-2' })]}
      />,
    );

    const [first, second] = screen.getAllByRole('checkbox');
    expect(first).toBeChecked();
    expect(second).not.toBeChecked();
  });

  it('does not let the operator toggle a box', () => {
    /**
     * The control for the test above. A writable checkbox would look correct
     * on first render and then drift from the server the moment anyone
     * clicked it — the exact rewrite the card is trying to prevent.
     */
    render(<QuestionChecklist questions={[question()]} />);

    expect(screen.getByRole('checkbox')).toHaveAttribute('readonly');
  });

  it('keeps the workflow tag out of the row’s accessible name', () => {
    /**
     * "Visually quiet" has an audible counterpart: a screen reader announcing
     * "campaigns" before every question would be a tag competing with the
     * text, which is what the card rules out.
     */
    render(<QuestionChecklist questions={[question({ workflow_target: 'WF3' })]} />);

    expect(screen.getByRole('checkbox')).toHaveAccessibleName('What do you sell?');
    const item = screen.getByRole('listitem');
    expect(within(item).getByText('campaigns')).toHaveAttribute('aria-hidden', 'true');
  });

  it('test_empty_state_links_to_prep', () => {
    /** The card's named case: the dead end is not a dead end. */
    render(<QuestionChecklist questions={[]} />);

    expect(screen.getByText(/no approved questionnaire/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /prepare questions in chat/i });
    expect(link).toHaveAttribute('href', '/chat');
  });

  it('shows no version and no checkboxes when the set is empty', () => {
    render(<QuestionChecklist questions={[]} version={3} />);

    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByText(/version/i)).toBeNull();
  });

  it('replaces the whole set when a new version is rendered', () => {
    /**
     * AC-3, satisfied by construction. There is no per-question client state,
     * so a question that no longer exists cannot leave anything behind — this
     * asserts the property rather than trusting the absence.
     */
    const { rerender } = render(
      <QuestionChecklist questions={APPROVED_SET} version={1} />,
    );
    expect(screen.getAllByRole('listitem')).toHaveLength(3);

    rerender(
      <QuestionChecklist
        questions={[question({ id: 'q-9', text: 'Only question in v2?' })]}
        version={2}
      />,
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent('Only question in v2?');
    expect(screen.queryByText('What do you sell?')).toBeNull();
    expect(screen.getByText('version 2')).toBeInTheDocument();
  });
});
