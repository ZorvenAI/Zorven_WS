/**
 * /privacy is for owners and admins: everyone else is sent to the dashboard
 * and never sees the erasure queue.
 */

import { render, screen, waitFor } from '@testing-library/react';

import PrivacyPage from '@/app/privacy/page';
import { useTenantRole } from '@/hooks/useTenantRole';

const replace = jest.fn();

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));
jest.mock('@/hooks/useAuth', () => ({ useAuth: jest.fn() }));
jest.mock('@/hooks/useTenantRole');
jest.mock('@/components/privacy/ErasureReviewQueue', () => ({
  __esModule: true,
  default: () => <div>erasure queue</div>,
}));
jest.mock('@/components/privacy/LegalHoldSettings', () => ({
  __esModule: true,
  default: () => <div>legal hold</div>,
}));
jest.mock('@/components/onboarding/RetentionSettings', () => ({
  __esModule: true,
  default: () => <div>retention</div>,
}));

const mockedRole = useTenantRole as jest.MockedFunction<typeof useTenantRole>;

function asRole(role: 'owner' | 'admin' | 'editor' | 'viewer') {
  const admin = role === 'owner' || role === 'admin';
  mockedRole.mockReturnValue({
    role,
    isOwner: role === 'owner',
    isAdmin: admin,
    canEdit: role !== 'viewer',
    canManageTeam: admin,
    canManageBilling: role === 'owner',
  } as ReturnType<typeof useTenantRole>);
}

beforeEach(() => replace.mockReset());

it.each(['owner', 'admin'] as const)('shows the queue and settings to an %s', (role) => {
  asRole(role);
  render(<PrivacyPage />);

  expect(screen.getByText('erasure queue')).toBeInTheDocument();
  expect(screen.getByText('legal hold')).toBeInTheDocument();
  expect(screen.getByText('retention')).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});

it.each(['editor', 'viewer'] as const)('sends an %s to the dashboard', async (role) => {
  asRole(role);
  render(<PrivacyPage />);

  await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'));
  expect(screen.queryByText('erasure queue')).toBeNull();
});
