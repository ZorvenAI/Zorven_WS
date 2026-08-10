/**
 * D-01 · the in-app calendar pane.
 *
 * The card names `test_viewer_readonly` here — RBAC at the component level.
 *
 * `now` is injected so the grid is not clock-dependent; a calendar test that
 * passes in January and fails in February is worse than no test, because the
 * failure looks like a regression.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import CalendarPane from '@/components/onboarding/CalendarPane';
import {
  cancelMeeting,
  createMeeting,
  listMeetings,
  listSessions,
  type ScheduledMeeting,
} from '@/lib/onboarding-sessions';
import { useTenantRole } from '@/hooks/useTenantRole';

jest.mock('@/lib/onboarding-sessions', () => ({
  ...jest.requireActual('@/lib/onboarding-sessions'),
  listMeetings: jest.fn(),
  listSessions: jest.fn(),
  createMeeting: jest.fn(),
  cancelMeeting: jest.fn(),
  /**
   * Pinned to UTC. The real implementation reads the machine's Intl zone, so
   * "booked Europe/London" only renders when the viewer's zone differs from
   * the booking's — and the suite would have failed for anyone running it in
   * London, including a CI runner configured that way. A test whose result
   * depends on where it runs reports geography, not correctness.
   */
  viewerTimezone: () => 'UTC',
}));
jest.mock('@/hooks/useTenantRole');

const mockedMeetings = listMeetings as jest.MockedFunction<typeof listMeetings>;
const mockedSessions = listSessions as jest.MockedFunction<typeof listSessions>;
const mockedCreate = createMeeting as jest.MockedFunction<typeof createMeeting>;
const mockedCancel = cancelMeeting as jest.MockedFunction<typeof cancelMeeting>;
const mockedRole = useTenantRole as jest.MockedFunction<typeof useTenantRole>;

/** A Tuesday, mid-month, well away from any DST boundary. */
const NOW = new Date('2024-06-11T09:00:00Z');

const MEETING: ScheduledMeeting = {
  id: 'm-1',
  session: 'sess-1',
  company: 'Kalyani Roasters',
  title: 'Kickoff',
  starts_at: '2024-06-12T13:00:00Z',
  ends_at: '2024-06-12T14:00:00Z',
  timezone: 'Europe/London',
  status: 'SCHEDULED',
};

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

beforeEach(() => {
  jest.clearAllMocks();
  mockedMeetings.mockResolvedValue([MEETING]);
  mockedSessions.mockResolvedValue([
    {
      id: 'sess-1',
      company: 'Kalyani Roasters',
      status: 'PREPARING',
      questionnaire: null,
      created_at: '2024-06-01T00:00:00Z',
      updated_at: '2024-06-01T00:00:00Z',
    },
  ]);
});

describe('CalendarPane', () => {
  it('renders a month grid with the meeting on it', async () => {
    asRole('admin');
    render(<CalendarPane now={NOW} />);

    expect(await screen.findByText(/Kickoff/)).toBeInTheDocument();
    // Six weeks of squares, so the grid shape does not move month to month.
    expect(screen.getAllByRole('gridcell')).toHaveLength(42);
  });

  it('switches to a week view', async () => {
    asRole('admin');
    render(<CalendarPane now={NOW} />);
    await screen.findByText(/Kickoff/);

    fireEvent.click(screen.getByRole('button', { name: /week/i }));

    await waitFor(() => expect(screen.getAllByRole('gridcell')).toHaveLength(7));
  });

  it('asks the server for the window it is showing', async () => {
    /**
     * The narrowing is server-side (D-01 PR 1). A component that fetched
     * everything and filtered here would work until the tenant had a year of
     * meetings.
     */
    asRole('admin');
    render(<CalendarPane now={NOW} />);

    await waitFor(() => expect(mockedMeetings).toHaveBeenCalled());
    const [from, to] = mockedMeetings.mock.calls[0];
    expect(from.getTime()).toBeLessThan(NOW.getTime());
    expect(to.getTime()).toBeGreaterThan(NOW.getTime());
  });

  it('shows the booking zone when it differs from the viewer’s', async () => {
    /**
     * AC-2's human half. The operator agreed "14:00 in London" with the brand
     * owner; a colleague reading this in another zone needs both that and
     * their own local time, or they will quote the wrong one back.
     */
    asRole('admin');
    render(<CalendarPane now={NOW} />);

    expect(await screen.findByText(/booked Europe\/London/)).toBeInTheDocument();
  });

  it('does not render a cancelled meeting', async () => {
    asRole('admin');
    mockedMeetings.mockResolvedValue([{ ...MEETING, status: 'CANCELLED' }]);

    render(<CalendarPane now={NOW} />);

    await waitFor(() => expect(mockedMeetings).toHaveBeenCalled());
    expect(screen.queryByText(/Kickoff/)).toBeNull();
  });

  it('test_viewer_readonly', async () => {
    /**
     * The card's named case. Absent, not disabled — E-01's precedent, and for
     * the same reason: a greyed control with a live endpoint behind it is not
     * read-only.
     */
    asRole('viewer');
    render(<CalendarPane now={NOW} />);

    await screen.findByText(/Kickoff/);

    expect(screen.queryByRole('button', { name: /schedule a meeting/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^cancel$/i })).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('still shows a viewer the calendar itself', async () => {
    /**
     * The control. A pane that rendered nothing for a Viewer would pass the
     * test above while failing AC-3, which grants "a read-only calendar".
     */
    asRole('viewer');
    render(<CalendarPane now={NOW} />);

    expect(await screen.findByText(/Kickoff/)).toBeInTheDocument();
    expect(screen.getByRole('grid')).toBeInTheDocument();
  });

  it('lets an editor schedule a meeting', async () => {
    /**
     * AC-1. The form is real rather than a button that opens nothing — an
     * affordance that does not do what it says is worse than a missing one.
     */
    asRole('editor');
    mockedCreate.mockResolvedValue(MEETING);
    render(<CalendarPane now={NOW} />);
    await screen.findByText(/Kickoff/);

    fireEvent.change(screen.getByLabelText(/starts/i), {
      target: { value: '2024-06-20T14:00' },
    });
    fireEvent.click(screen.getByRole('button', { name: /schedule a meeting/i }));

    await waitFor(() => expect(mockedCreate).toHaveBeenCalled());
    const draft = mockedCreate.mock.calls[0][0];
    expect(draft.session).toBe('sess-1');
    // Sent as a UTC instant, with the zone alongside — never an offset.
    expect(draft.starts_at).toMatch(/Z$/);
    expect(draft.timezone).toBeTruthy();
    expect(draft.timezone).not.toMatch(/^[+-]\d/);
  });

  it('reports a scheduling failure instead of silently doing nothing', async () => {
    asRole('editor');
    mockedCreate.mockRejectedValue(new Error('API 400: overlaps'));
    render(<CalendarPane now={NOW} />);
    await screen.findByText(/Kickoff/);

    fireEvent.change(screen.getByLabelText(/starts/i), {
      target: { value: '2024-06-20T14:00' },
    });
    fireEvent.click(screen.getByRole('button', { name: /schedule a meeting/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('overlaps');
  });

  it('cancels a meeting and reloads', async () => {
    asRole('editor');
    mockedCancel.mockResolvedValue({ ...MEETING, status: 'CANCELLED' });
    render(<CalendarPane now={NOW} />);
    await screen.findByText(/Kickoff/);

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    await waitFor(() => expect(mockedCancel).toHaveBeenCalledWith('m-1'));
    expect(mockedMeetings).toHaveBeenCalledTimes(2);
  });

  it('clears the grid rather than showing last month’s meetings', async () => {
    asRole('admin');
    mockedMeetings.mockRejectedValue(new Error('network'));
    jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<CalendarPane now={NOW} />);

    await waitFor(() => expect(screen.queryByText(/Kickoff/)).toBeNull());
    expect(screen.getByRole('grid')).toBeInTheDocument();
  });

  it('places a meeting on the viewer’s local day, not the UTC one', async () => {
    /**
     * A meeting at 23:00 UTC belongs to the next day for anyone east of
     * Greenwich. Grouping by the UTC date would put it on the wrong square —
     * visible to a user, invisible to a test that only checks it rendered.
     */
    asRole('admin');
    const late = { ...MEETING, id: 'm-2', starts_at: '2024-06-12T23:30:00Z' };
    mockedMeetings.mockResolvedValue([late]);

    render(<CalendarPane now={NOW} />);
    await screen.findByText(/Kickoff/);

    const local = new Date(late.starts_at);
    const cell = screen.getByRole('gridcell', { name: local.toDateString() });
    expect(within(cell).getByText(/Kickoff/)).toBeInTheDocument();
  });
});
