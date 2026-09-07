/**
 * M-03 AC-3 · Retention settings warning when shortening.
 *
 * The backlog names this file explicitly. AC-3 exists because the alternative
 * is "we lost eight months of onboarding data by changing a dropdown."
 *
 * The component uses a preview-then-save flow: shortening calls
 * previewRetentionConfig (PATCH ?preview=true) which returns impact without
 * persisting, then updateRetentionConfig only fires on Confirm. This test
 * suite verifies that contract — previewRetentionConfig is the only call on
 * Save for a shortening, and updateRetentionConfig fires only on Confirm.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import RetentionSettings from '@/components/onboarding/RetentionSettings';
import {
  getRetentionConfig,
  previewRetentionConfig,
  updateRetentionConfig,
} from '@/lib/onboarding-sessions';
import { useTenantRole } from '@/hooks/useTenantRole';

jest.mock('@/lib/onboarding-sessions', () => ({
  ...jest.requireActual('@/lib/onboarding-sessions'),
  getRetentionConfig: jest.fn(),
  previewRetentionConfig: jest.fn(),
  updateRetentionConfig: jest.fn(),
}));
jest.mock('@/hooks/useTenantRole');

const mockedGet = getRetentionConfig as jest.MockedFunction<typeof getRetentionConfig>;
const mockedPreview = previewRetentionConfig as jest.MockedFunction<
  typeof previewRetentionConfig
>;
const mockedUpdate = updateRetentionConfig as jest.MockedFunction<
  typeof updateRetentionConfig
>;
const mockedRole = useTenantRole as jest.MockedFunction<typeof useTenantRole>;

function asRole(role: 'admin' | 'editor' | 'viewer') {
  mockedRole.mockReturnValue({
    role,
    isOwner: role === 'admin',
    isAdmin: role === 'admin',
    canEdit: role === 'admin' || role === 'editor',
    canManageTeam: role === 'admin',
    canManageBilling: false,
  } as ReturnType<typeof useTenantRole>);
}

const CONFIG = {
  retention_days: 365,
  is_default: false,
  next_enforcement_run: '2026-09-08T03:00:00Z',
};

beforeEach(() => {
  jest.clearAllMocks();
  mockedGet.mockResolvedValue(CONFIG);
  asRole('admin');
});

test('renders current retention value after loading', async () => {
  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });
});

test('non-admin sees read-only display without form controls', async () => {
  asRole('viewer');
  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByText(/365 days/)).toBeInTheDocument();
  });
  expect(screen.queryByLabelText(/Keep onboarding evidence/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
});

test('save button disabled when value unchanged', async () => {
  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });
  expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
});

test('save button disabled for invalid input', async () => {
  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  const input = screen.getByLabelText(/Keep onboarding evidence/);
  fireEvent.change(input, { target: { value: '' } });

  expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
});

test('shortening shows warning before save', async () => {
  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  const input = screen.getByLabelText(/Keep onboarding evidence/);
  fireEvent.change(input, { target: { value: '30' } });

  expect(screen.getByText(/shortening retention may delete/i)).toBeInTheDocument();
});

test('shortening calls preview (not update) and shows impact', async () => {
  mockedPreview.mockResolvedValue({
    retention_days: 30,
    previous_days: 365,
    is_default: false,
    next_enforcement_run: '2026-09-08T03:00:00Z',
    impact: {
      subjects: 4,
      sessions: 7,
      enforced_at: '2026-09-08T03:00:00Z',
    },
  });

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  fireEvent.change(screen.getByLabelText(/Keep onboarding evidence/), {
    target: { value: '30' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => {
    expect(screen.getByText(/4 subject/)).toBeInTheDocument();
    expect(screen.getByText(/7 session/)).toBeInTheDocument();
  });

  expect(mockedPreview).toHaveBeenCalledWith(30);
  expect(mockedUpdate).not.toHaveBeenCalled();

  expect(screen.getByRole('button', { name: /confirm shorter retention/i }))
    .toBeInTheDocument();
  expect(screen.getByRole('button', { name: /revert/i }))
    .toBeInTheDocument();
});

test('confirming after preview calls updateRetentionConfig', async () => {
  mockedPreview.mockResolvedValue({
    retention_days: 30,
    previous_days: 365,
    is_default: false,
    next_enforcement_run: '2026-09-08T03:00:00Z',
    impact: {
      subjects: 2,
      sessions: 3,
      enforced_at: '2026-09-08T03:00:00Z',
    },
  });
  mockedUpdate.mockResolvedValue({
    retention_days: 30,
    previous_days: 365,
    is_default: false,
    next_enforcement_run: '2026-09-08T03:00:00Z',
  });

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  fireEvent.change(screen.getByLabelText(/Keep onboarding evidence/), {
    target: { value: '30' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => {
    expect(screen.getByRole('button', { name: /confirm shorter retention/i }))
      .toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole('button', { name: /confirm shorter retention/i }));

  await waitFor(() => {
    expect(screen.getByDisplayValue('30')).toBeInTheDocument();
  });
  expect(mockedUpdate).toHaveBeenCalledWith(30);
  expect(screen.queryByText(/subject/)).not.toBeInTheDocument();
});

test('reverting after preview restores original value without saving', async () => {
  mockedPreview.mockResolvedValue({
    retention_days: 30,
    previous_days: 365,
    is_default: false,
    next_enforcement_run: '2026-09-08T03:00:00Z',
    impact: {
      subjects: 1,
      sessions: 1,
      enforced_at: '2026-09-08T03:00:00Z',
    },
  });

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  fireEvent.change(screen.getByLabelText(/Keep onboarding evidence/), {
    target: { value: '30' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => {
    expect(screen.getByRole('button', { name: /revert/i }))
      .toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole('button', { name: /revert/i }));

  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });
  expect(mockedUpdate).not.toHaveBeenCalled();
});

test('increasing retention saves directly without preview', async () => {
  mockedUpdate.mockResolvedValue({
    retention_days: 730,
    previous_days: 365,
    is_default: false,
    next_enforcement_run: '2026-09-08T03:00:00Z',
  });

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  fireEvent.change(screen.getByLabelText(/Keep onboarding evidence/), {
    target: { value: '730' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => {
    expect(screen.getByDisplayValue('730')).toBeInTheDocument();
  });
  expect(mockedPreview).not.toHaveBeenCalled();
  expect(mockedUpdate).toHaveBeenCalledWith(730);
});

test('shows platform default hint when is_default is true', async () => {
  mockedGet.mockResolvedValue({
    retention_days: 365,
    is_default: true,
    next_enforcement_run: '2026-09-08T03:00:00Z',
  });

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByText(/platform default/i)).toBeInTheDocument();
  });
});

test('shows error on API failure', async () => {
  mockedGet.mockResolvedValue(CONFIG);
  mockedUpdate.mockRejectedValue(new Error('API 403: Forbidden'));

  render(<RetentionSettings />);
  await waitFor(() => {
    expect(screen.getByDisplayValue('365')).toBeInTheDocument();
  });

  fireEvent.change(screen.getByLabelText(/Keep onboarding evidence/), {
    target: { value: '730' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => {
    expect(screen.getByText(/API 403: Forbidden/)).toBeInTheDocument();
  });
});
