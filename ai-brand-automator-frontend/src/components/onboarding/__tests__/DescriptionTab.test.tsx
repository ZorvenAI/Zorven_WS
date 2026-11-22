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
    description:
      '## Business Identity\nAcme Corp in retail\n\n## Target Audience\nSmall businesses',
    has_clean_transcript: true,
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
    description: '',
    has_clean_transcript: false,
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
    description: '## Business Identity\nSomething',
    has_clean_transcript: true,
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
    description: '## Business Identity\nContent here',
    has_clean_transcript: true,
  });

  await act(async () => {
    render(<DescriptionTab sessionId={SESSION_ID} />);
  });

  await waitFor(() => {
    expect(screen.getByText('Brand-Building Description')).toBeInTheDocument();
  });
});
