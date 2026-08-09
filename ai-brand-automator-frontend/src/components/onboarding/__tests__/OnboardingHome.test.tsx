/**
 * E-01 · the Onboarding Interface landing view.
 *
 * The card names `test_viewer_affordances_absent` here, and AC-3 is explicit
 * about what "absent" means: "the buttons are absent, not merely disabled with
 * a hidden working endpoint behind them". A test that only asserted a button
 * was disabled would pass on exactly the implementation the AC rules out, so
 * these assert absence by query and then assert the read-only page still shows
 * the data a Viewer is entitled to.
 */

import { render, screen, waitFor } from '@testing-library/react';

import OnboardingHome from '@/components/onboarding/OnboardingHome';
import { listRecordings, listSessions } from '@/lib/onboarding-sessions';
import { useTenantRole } from '@/hooks/useTenantRole';

jest.mock('@/lib/onboarding-sessions', () => ({
  ...jest.requireActual('@/lib/onboarding-sessions'),
  listSessions: jest.fn(),
  listRecordings: jest.fn(),
}));
jest.mock('@/hooks/useTenantRole');

const mockedSessions = listSessions as jest.MockedFunction<typeof listSessions>;
const mockedRecordings = listRecordings as jest.MockedFunction<typeof listRecordings>;
const mockedRole = useTenantRole as jest.MockedFunction<typeof useTenantRole>;

function asRole(role: 'admin' | 'editor' | 'viewer') {
  mockedRole.mockReturnValue({
    role,
    isOwner: false,
    isAdmin: role === 'admin',
    canEdit: role === 'admin' || role === 'editor',
    canManageTeam: role === 'admin',
    canManageBilling: false,
  } as ReturnType<typeof useTenantRole>);
}

const SESSION = {
  id: 'sess-1',
  company: 'company-1',
  status: 'READY' as const,
  questionnaire: 'q-1',
  created_at: '2026-08-09T10:00:00Z',
  updated_at: '2026-08-09T11:00:00Z',
};

beforeEach(() => {
  jest.clearAllMocks();
  mockedSessions.mockResolvedValue([SESSION]);
  mockedRecordings.mockResolvedValue([]);
  asRole('admin');
});

describe('OnboardingHome', () => {
  it('renders the landing composition', async () => {
    render(<OnboardingHome />);

    // AC-1: the calendar pane, the sessions list and clear entry points.
    expect(await screen.findByRole('heading', { name: /schedule/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /sessions/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /prepare in chat/i })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /go to onboarding forms/i }),
    ).toBeInTheDocument();
  });

  it('shows a session with its §9.4 status chip', async () => {
    render(<OnboardingHome />);

    expect(await screen.findByText('company-1')).toBeInTheDocument();
    expect(screen.getByText('ready')).toBeInTheDocument();
  });

  it('test_viewer_affordances_absent', async () => {
    /**
     * The card's named case. Absent, not disabled — AC-3 rules out a greyed
     * button with a working endpoint behind it, so absence is asserted by
     * query rather than by checking a `disabled` attribute.
     */
    asRole('viewer');
    render(<OnboardingHome />);

    await screen.findByRole('heading', { name: /sessions/i });

    expect(screen.queryByRole('link', { name: /prepare in chat/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /go to onboarding forms/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /^open$/i })).toBeNull();
  });

  it('still shows a viewer the data they are entitled to', async () => {
    /**
     * The control. A page that rendered nothing for a Viewer would pass the
     * test above while failing AC-3, which says they "see sessions and
     * recordings".
     */
    asRole('viewer');
    render(<OnboardingHome />);

    expect(await screen.findByText('company-1')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /recordings/i })).toBeInTheDocument();
  });

  it('leads somewhere useful when there are no sessions', async () => {
    mockedSessions.mockResolvedValue([]);
    render(<OnboardingHome />);

    expect(await screen.findByText(/no onboarding sessions yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /prepare your first meeting in chat/i }),
    ).toBeInTheDocument();
  });

  it('clears the list rather than keeping stale rows when loading fails', async () => {
    mockedSessions.mockRejectedValue(new Error('network'));
    jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<OnboardingHome />);

    await waitFor(() =>
      expect(screen.getByText(/no onboarding sessions yet/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText('company-1')).toBeNull();
  });
});
