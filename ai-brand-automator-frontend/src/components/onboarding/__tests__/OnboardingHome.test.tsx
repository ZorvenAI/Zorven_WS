/**
 * OIA-UI-01 · Onboarding Home with toggle tabs.
 *
 * AC-7 (viewer affordances absent) retains the E-01 rule: absent, not
 * disabled — a greyed button with a working endpoint behind it does not
 * count, so the affordances are not rendered at all.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import OnboardingHome from '@/components/onboarding/OnboardingHome';
import { listRecordings, listSessions } from '@/lib/onboarding-sessions';
import { useTenantRole } from '@/hooks/useTenantRole';

jest.mock('@/lib/onboarding-sessions', () => ({
  ...jest.requireActual('@/lib/onboarding-sessions'),
  listSessions: jest.fn(),
  listRecordings: jest.fn(),
}));
jest.mock('@/hooks/useTenantRole');
jest.mock('@/components/onboarding/CalendarPane', () => ({
  __esModule: true,
  default: () => <section aria-label="Calendar" />,
}));
jest.mock('@/components/chat/ChatInterface', () => ({
  __esModule: true,
  ChatInterface: ({ defaultSidebarOpen: _dsb }: { defaultSidebarOpen?: boolean }) => (
    <section aria-label="AI Chat" />
  ),
}));

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
  company_name: 'company-1',
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
  it('renders the landing composition with tab bar', async () => {
    render(<OnboardingHome />);

    expect(await screen.findByRole('region', { name: /calendar/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /sessions/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /setup meeting/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /prepare in chat/i })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /go to forms/i }),
    ).toBeInTheDocument();
  });

  it('defaults to Setup Meeting tab with calendar visible', async () => {
    render(<OnboardingHome />);

    const meetingTab = await screen.findByRole('tab', { name: /setup meeting/i });
    expect(meetingTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('region', { name: /calendar/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /ai chat/i })).not.toBeInTheDocument();
  });

  it('switches to chat when Prepare in Chat is clicked', async () => {
    const user = userEvent.setup();
    render(<OnboardingHome />);

    await screen.findByRole('tab', { name: /setup meeting/i });
    await user.click(screen.getByRole('tab', { name: /prepare in chat/i }));

    expect(screen.getByRole('tab', { name: /prepare in chat/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // Lazy-loaded — wait for Suspense to resolve
    expect(await screen.findByRole('region', { name: /ai chat/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /calendar/i })).not.toBeInTheDocument();
  });

  it('switches back to calendar when Setup Meeting is clicked', async () => {
    const user = userEvent.setup();
    render(<OnboardingHome />);

    await screen.findByRole('tab', { name: /setup meeting/i });
    await user.click(screen.getByRole('tab', { name: /prepare in chat/i }));
    await screen.findByRole('region', { name: /ai chat/i });
    await user.click(screen.getByRole('tab', { name: /setup meeting/i }));

    expect(screen.getByRole('region', { name: /calendar/i })).toBeInTheDocument();
    // Chat stays mounted but hidden (preserves state)
    const chatRegion = screen.getByRole('region', { name: /ai chat/i });
    expect(chatRegion.closest('.hidden')).toBeTruthy();
  });

  it('shows a session with its status chip', async () => {
    render(<OnboardingHome />);

    expect(await screen.findByText('company-1')).toBeInTheDocument();
    expect(screen.getByText('ready')).toBeInTheDocument();
  });

  it('test_viewer_affordances_absent', async () => {
    asRole('viewer');
    render(<OnboardingHome />);

    await screen.findByRole('heading', { name: /sessions/i });

    expect(screen.queryByRole('tab', { name: /prepare in chat/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /go to forms/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /^open$/i })).toBeNull();
    // Viewer still sees the Setup Meeting tab
    expect(screen.getByRole('tab', { name: /setup meeting/i })).toBeInTheDocument();
  });

  it('still shows a viewer the data they are entitled to', async () => {
    asRole('viewer');
    render(<OnboardingHome />);

    expect(await screen.findByText('company-1')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /recordings/i })).toBeInTheDocument();
  });

  it('empty-state button switches to chat tab instead of navigating', async () => {
    const user = userEvent.setup();
    mockedSessions.mockResolvedValue([]);
    render(<OnboardingHome />);

    const chatButton = await screen.findByRole('button', {
      name: /prepare your first meeting in chat/i,
    });
    await user.click(chatButton);

    expect(screen.getByRole('tab', { name: /prepare in chat/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(await screen.findByRole('region', { name: /ai chat/i })).toBeInTheDocument();
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
