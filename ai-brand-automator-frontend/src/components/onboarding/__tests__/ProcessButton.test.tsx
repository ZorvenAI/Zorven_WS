/**
 * J-01 · ProcessButton and coverage warning modal.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import ProcessButton from '@/components/onboarding/ProcessButton';
import type { WorkflowTarget } from '@/lib/onboarding-sessions';

jest.mock('@/lib/onboarding-sessions', () => ({
  triggerProcess: jest.fn(),
  formatTime: (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  },
}));

const mockTrigger = jest.requireMock('@/lib/onboarding-sessions')
  .triggerProcess as jest.Mock;

beforeEach(() => {
  mockTrigger.mockReset();
  mockTrigger.mockResolvedValue({ job_id: 'job-1', status: 'PROCESSING' });
});

const goodCoverage: Record<WorkflowTarget, number> = {
  WF1: 0.8,
  WF2: 0.7,
  WF3: 0.9,
};

const lowCoverage: Record<WorkflowTarget, number> = {
  WF1: 0.8,
  WF2: 0.3,
  WF3: 0.9,
};

it('renders enabled button in GATHERED state', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={goodCoverage}
    />,
  );
  const btn = screen.getByRole('button', { name: /Process onboarding data/i });
  expect(btn).not.toBeDisabled();
});

it('renders disabled button with reason in DRAFT state', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="DRAFT"
      coverage={null}
    />,
  );
  const btn = screen.getByRole('button', { name: /Process onboarding data/i });
  expect(btn).toBeDisabled();
  expect(screen.getByText(/Complete the meeting/)).toBeInTheDocument();
});

it('renders disabled button in MEETING_LIVE state', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="MEETING_LIVE"
      coverage={null}
    />,
  );
  expect(screen.getByText(/End the meeting/)).toBeInTheDocument();
});

it('shows processing indicator when status is PROCESSING', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="PROCESSING"
      coverage={null}
    />,
  );
  expect(screen.getByText(/Processing onboarding data…/)).toBeInTheDocument();
});

it('shows review complete and re-run button when REVIEW_PENDING', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="REVIEW_PENDING"
      coverage={goodCoverage}
    />,
  );
  expect(screen.getByText(/Processing complete/)).toBeInTheDocument();
  const btn = screen.getByRole('button', { name: /Re-process onboarding data/i });
  expect(btn).not.toBeDisabled();
});

it('dispatches without modal when coverage is good', async () => {
  const onDispatch = jest.fn();
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={goodCoverage}
      onDispatch={onDispatch}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Process onboarding data/i }));
  await waitFor(() => {
    expect(mockTrigger).toHaveBeenCalledWith('sess-1');
  });
});

it('shows coverage warning when below threshold', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={lowCoverage}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Process onboarding data/i }));
  expect(screen.getByText(/Some areas have low coverage/)).toBeInTheDocument();
});

it('dispatches on "Continue anyway"', async () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={lowCoverage}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Process onboarding data/i }));
  fireEvent.click(screen.getByText('Continue anyway'));
  await waitFor(() => {
    expect(mockTrigger).toHaveBeenCalledWith('sess-1');
  });
});

it('closes modal on "Return to capture"', () => {
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={lowCoverage}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Process onboarding data/i }));
  expect(screen.getByText(/Some areas have low coverage/)).toBeInTheDocument();
  fireEvent.click(screen.getByText('Return to capture'));
  expect(screen.queryByText(/Some areas have low coverage/)).not.toBeInTheDocument();
});

it('shows error on dispatch failure', async () => {
  mockTrigger.mockRejectedValue(new Error('OIA unreachable'));
  render(
    <ProcessButton
      sessionId="sess-1"
      status="GATHERED"
      coverage={goodCoverage}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Process onboarding data/i }));
  await waitFor(() => {
    expect(screen.getByText('OIA unreachable')).toBeInTheDocument();
  });
});
