/**
 * Erasure review queue.
 *
 * Only `apiClient` is stubbed, so `erasure-review.ts` runs for real and these
 * tests also pin the paths and bodies the component sends.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ErasureReviewQueue from '@/components/privacy/ErasureReviewQueue';
import { apiClient } from '@/lib/api';
import type { ErasureReviewItem } from '@/lib/erasure-review';

jest.mock('@/lib/api', () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));

const get = apiClient.get as jest.Mock;
const post = apiClient.post as jest.Mock;

const REASON = 'Signed agreement may be needed for a dispute.';

function ok(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

function item(overrides: Partial<ErasureReviewItem> = {}): ErasureReviewItem {
  return {
    id: 42,
    subject_name: 'Maria Rossi',
    reason: 'retention_enforcement',
    requested_at: '2026-11-02T10:00:00Z',
    requested_by: 'naveen',
    days_waiting: 3,
    overdue: false,
    held: [
      {
        session_id: '6',
        company_name: 'Pomodoro',
        records: [{ record_number: 'MR-000085-v1', status: 'COMPLETED' }],
      },
    ],
    review_status: 'PENDING',
    reviewed_by: null,
    reviewed_at: null,
    review_reason: '',
    hold_until: null,
    erase_in_progress: false,
    last_error: '',
    erased_signed_records: [],
    default_hold_until: '2033-11-28',
    ...overrides,
  };
}

/** Serve the three list calls: pending, kept, erased. */
function serve(
  pending: ErasureReviewItem[],
  kept: ErasureReviewItem[] = [],
  erased: ErasureReviewItem[] = [],
) {
  get.mockImplementation(async (path: string) => {
    if (path.endsWith('?status=KEPT')) return ok(kept);
    if (path.endsWith('?status=ERASED')) return ok(erased);
    return ok(pending);
  });
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

async function openRow() {
  const user = userEvent.setup();
  render(<ErasureReviewQueue />);
  const row = await screen.findByTestId('review-42');
  return { user, row };
}

describe('the queue', () => {
  it('lists each held request with what it holds', async () => {
    serve([item()]);
    const { row } = await openRow();

    expect(within(row).getByText('Maria Rossi')).toBeInTheDocument();
    expect(within(row).getByText(/Pomodoro: MR-000085-v1/)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/onboarding/erasure/review/');
    expect(row).toHaveAttribute('data-overdue', 'false');
  });

  it('flags a request close to the one-month deadline', async () => {
    serve([item({ days_waiting: 26, overdue: true })]);
    const { row } = await openRow();

    expect(row).toHaveAttribute('data-overdue', 'true');
    expect(within(row).getByText(/one-month deadline/)).toBeInTheDocument();
  });

  it('says when nothing is waiting', async () => {
    serve([]);
    render(<ErasureReviewQueue />);

    expect(await screen.findByText('Nothing is waiting for a decision.')).toBeInTheDocument();
  });
});

describe('keeping', () => {
  it('needs a reason, then keeps until the chosen date', async () => {
    serve([item()]);
    const { user, row } = await openRow();
    post.mockResolvedValue(ok(item({ review_status: 'KEPT' })));

    await user.click(within(row).getByRole('button', { name: 'Keep under legal hold' }));
    const confirm = within(row).getByRole('button', { name: 'Confirm legal hold' });
    expect(within(row).getByLabelText('Keep until')).toHaveValue('2033-11-28');
    expect(confirm).toBeDisabled();

    await user.type(within(row).getByLabelText(/Reason/), 'too short');
    expect(confirm).toBeDisabled();
    await user.clear(within(row).getByLabelText(/Reason/));
    await user.type(within(row).getByLabelText(/Reason/), REASON);
    await user.click(confirm);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/onboarding/erasure/review/42/keep/', {
        reason: REASON,
        hold_until: '2033-11-28',
      }),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('under legal hold');
  });
});

describe('erasing anyway', () => {
  it('stays disabled until the name is typed exactly', async () => {
    serve([item()]);
    const { user, row } = await openRow();
    post.mockResolvedValue(ok(item({ erase_in_progress: true }), 202));

    await user.click(within(row).getByRole('button', { name: 'Erase anyway' }));
    expect(within(row).getByText(/cannot be undone/)).toBeInTheDocument();
    const confirm = within(row).getByRole('button', { name: 'Erase permanently' });

    await user.type(within(row).getByLabelText(/Reason/), REASON);
    await user.type(within(row).getByLabelText(/to confirm/), 'maria rossi');
    expect(confirm).toBeDisabled();

    await user.clear(within(row).getByLabelText(/to confirm/));
    await user.type(within(row).getByLabelText(/to confirm/), 'Maria Rossi');
    await user.click(confirm);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/onboarding/erasure/review/42/erase/', {
        reason: REASON,
        confirm_subject: 'Maria Rossi',
      }),
    );
  });

  it('shows the server’s reason when a decision is refused', async () => {
    serve([item()]);
    const { user, row } = await openRow();
    post.mockResolvedValue(
      ok({ error: 'not_pending', detail: 'This request is not awaiting review.' }, 409),
    );

    await user.click(within(row).getByRole('button', { name: 'Keep under legal hold' }));
    await user.type(within(row).getByLabelText(/Reason/), REASON);
    await user.click(within(row).getByRole('button', { name: 'Confirm legal hold' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This request is not awaiting review.',
    );
  });

  it('offers no decision while an erasure is already running', async () => {
    serve([item({ erase_in_progress: true })]);
    const { row } = await openRow();

    expect(within(row).getByText('Erasure was chosen and is running.')).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Erase anyway' })).toBeNull();
  });
});

describe('decided requests', () => {
  it('show who decided, when, why, and what was erased', async () => {
    serve(
      [],
      [
        item({
          id: 1,
          review_status: 'KEPT',
          reviewed_by: 'naveen',
          reviewed_at: '2026-11-20T10:00:00Z',
          review_reason: REASON,
          hold_until: '2033-11-20',
        }),
      ],
      [
        item({
          id: 2,
          subject_name: 'Luca Bianchi',
          review_status: 'ERASED',
          reviewed_by: 'naveen',
          reviewed_at: '2026-11-21T10:00:00Z',
          review_reason: 'Subject withdrew; no dispute expected.',
          erased_signed_records: [
            {
              record_number: 'MR-000090-v1',
              status: 'COMPLETED',
              content_hash: 'ab'.repeat(32),
              issued_at: null,
              completed_at: null,
            },
          ],
        }),
      ],
    );
    const user = userEvent.setup();
    render(<ErasureReviewQueue />);

    await user.click(await screen.findByRole('tab', { name: 'Decided' }));

    const list = screen.getByRole('list', { name: 'Decided requests' });
    const [erased, kept] = within(list).getAllByRole('listitem');
    expect(erased).toHaveTextContent('Erased on review by naveen');
    expect(erased).toHaveTextContent('Erased records: MR-000090-v1');
    expect(kept).toHaveTextContent('Kept under legal hold by naveen');
    expect(kept).toHaveTextContent(`Reason: ${REASON}`);
  });
});
