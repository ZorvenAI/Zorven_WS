/**
 * F-01 · DescriptionTab — renders brand-building description from T3.
 */

import { render, screen, waitFor, act } from '@testing-library/react';

import DescriptionTab from '@/components/onboarding/DescriptionTab';

const SESSION_ID = 'test-session-123';

function mockFetch(data: object, status = 200) {
  return jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

function meeting(id: number, description: string, transcript_clean = '') {
  return {
    recording_id: id,
    started_at: '2026-11-24T10:00:00Z',
    description,
    transcript_clean,
  };
}

beforeEach(() => {
  jest.restoreAllMocks();
});

it('shows loading spinner initially', () => {
  // Never resolves so we stay in loading state.
  global.fetch = jest.fn().mockReturnValue(new Promise(() => {}));

  const { container } = render(<DescriptionTab sessionId={SESSION_ID} />);

  expect(container.querySelector('.animate-spin')).toBeTruthy();
});

it('renders description sections when data loads', async () => {
  global.fetch = mockFetch({
    meetings: [meeting(1, '## Business Identity\nAcme Corp in retail\n\n## Target Audience\nSmall businesses')],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText('Business Identity')).toBeInTheDocument();
  });
  expect(screen.getByText('Target Audience')).toBeInTheDocument();
  expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
});

it('shows empty state when no description', async () => {
  global.fetch = mockFetch({
    meetings: [meeting(1, '')],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText(/No description available/)).toBeInTheDocument();
  });
});

it('shows error state on fetch failure', async () => {
  global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });
  expect(screen.getByText('Retry')).toBeInTheDocument();
});

it('shows error when API returns non-200', async () => {
  global.fetch = mockFetch({ error: 'not found' }, 404);

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText(/HTTP 404/)).toBeInTheDocument();
  });
});

it('renders the refresh button', async () => {
  global.fetch = mockFetch({
    meetings: [meeting(1, '## Business Identity\nSomething')],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });
});

it('renders heading "Brand-Building Description"', async () => {
  global.fetch = mockFetch({
    meetings: [meeting(1, '## Business Identity\nContent here')],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText('Brand-Building Description')).toBeInTheDocument();
  });
});

it('renders the Agreements section of a description', async () => {
  global.fetch = mockFetch({
    meetings: [
      meeting(1, '## Agreements\n- Budget split evenly between dine-in and takeout'),
    ],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText('Agreements')).toBeInTheDocument();
  });
  expect(screen.getByText(/Budget split evenly/)).toBeInTheDocument();
  expect(screen.queryByRole('tablist', { name: 'Meetings' })).toBeNull();
});

it('lets the operator switch between meetings of one session', async () => {
  global.fetch = mockFetch({
    meetings: [
      meeting(1, '## Agreements\n- First meeting agreement'),
      meeting(2, '## Agreements\n- Second meeting agreement'),
    ],
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  // The most recent meeting is shown first.
  await waitFor(() => {
    expect(screen.getByText(/Second meeting agreement/)).toBeInTheDocument();
  });
  expect(screen.queryByText(/First meeting agreement/)).toBeNull();

  await act(async () => {
    screen.getByRole('tab', { name: /Meeting 1/ }).click();
  });

  expect(screen.getByText(/First meeting agreement/)).toBeInTheDocument();
  expect(screen.queryByText(/Second meeting agreement/)).toBeNull();
});
