/**
 * Signed meeting records · step 2 — the Documents tab.
 *
 * The API client is the only thing stubbed, so `meeting-records.ts` runs for
 * real: these tests cover the tab and its client together, including the
 * exact paths and bodies sent.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import DocumentsTab from '@/components/onboarding/DocumentsTab';
import { apiClient } from '@/lib/api';
import { useTenantRole } from '@/hooks/useTenantRole';
import type {
  MeetingWithRecord,
  ReadinessItem,
  RecordDetail,
  RecordStatus,
  Signatory,
} from '@/lib/meeting-records';

jest.mock('@/lib/api', () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));
jest.mock('@/hooks/useTenantRole');

const get = apiClient.get as jest.Mock;
const post = apiClient.post as jest.Mock;
const put = apiClient.put as jest.Mock;
const mockedRole = useTenantRole as jest.MockedFunction<typeof useTenantRole>;

const SESSION = '6';
const HASH = '9f2c'.repeat(16);

function ok(body: unknown, status = 200) {
  return { ok: true, status, json: async () => body, blob: async () => new Blob(['%PDF']) };
}

function refused(status: number, body: unknown) {
  return { ok: false, status, json: async () => body };
}

function summary(status: RecordStatus, overrides: Partial<RecordDetail> = {}) {
  return {
    id: 11,
    record_number: 'MR-000085-v1',
    version: 1,
    status,
    recording_id: 85,
    session_id: 6,
    content_hash: status === 'DRAFT' ? '' : HASH,
    clause_version: status === 'DRAFT' ? '' : '2026-11-draft-1',
    issued_at: status === 'DRAFT' ? null : '2026-11-25T10:00:00Z',
    voided_at: null,
    void_reason: '',
    supersedes: null,
    created_at: '2026-11-25T09:00:00Z',
    ...overrides,
  };
}

function check(code: string, okValue: boolean, blocking = true): ReadinessItem {
  return {
    code,
    ok: okValue,
    blocking,
    fields: [],
    message: `${code} ${okValue ? 'passed' : 'failed'}`,
  };
}

const READY = [check('content', true), check('party_details', true), check('completeness', true)];

function detail(
  status: RecordStatus,
  readiness: ReadinessItem[] = status === 'DRAFT' ? READY : [],
  overrides: Partial<RecordDetail> = {},
): RecordDetail {
  return {
    ...summary(status, overrides),
    readiness,
    events: [
      {
        event_type: 'CREATED',
        label: 'Draft prepared',
        actor: 'naveen',
        occurred_at: '2026-11-25T09:00:00Z',
      },
    ],
    document: {
      record: { number: 'MR-000085-v1', version: 1, supersedes: null },
      clause: { version: '2026-11-draft-1', text: 'Clause.' },
      parties: {
        agency: { name: 'Zorven Agency' },
        client: {
          name: 'Pomodoro',
          legal_name: 'Pomodoro Trattoria LLC',
          registered_address: '14 Main Street',
          signatory_name: 'Maria Rossi',
          signatory_title: 'Owner',
          signatory_email: 'maria@example.com',
          registration_number: '',
        },
      },
      meeting: {
        recording_id: 85,
        started_at: '2026-11-23T19:31:00Z',
        stopped_at: null,
        duration_s: 1810,
      },
      attendees: [],
      consent: null,
      completeness: { state: 'complete', missing_s: 0, note: '' },
      agreements: {
        preamble: '',
        items: [
          { number: 'A-1', text: '**Budget split** evenly.' },
          { number: 'A-2', text: 'Contract review before launch.' },
        ],
      },
      description: '',
      transcript: ['Naveen: Shall we split the budget?', 'Maria Rossi: Yes, agreed.'],
    },
    signatories: [
      signatory({ id: 1, party: 'AGENCY', party_name: 'Zorven Agency', name: 'Naveen H', email: 'naveen@agency.test' }),
      signatory({ id: 2 }),
    ],
    remarks_to_acknowledge: {},
    you: null,
    consent: { version: '2026-11-draft-1', text: 'I agree to sign this document electronically.' },
    ...overrides,
  };
}

function signatory(overrides: Partial<Signatory> = {}): Signatory {
  return {
    id: 2,
    party: 'CLIENT',
    party_name: 'Pomodoro Trattoria LLC',
    name: 'Maria Rossi',
    title: 'Owner',
    email: 'maria@example.com',
    required: true,
    status: 'PENDING',
    signed_at: null,
    declined_at: null,
    remarks: '',
    decline_reason: '',
    method: '',
    typed_name: '',
    ip_address: null,
    link_expires_at: null,
    remarks_acknowledged_at: null,
    ...overrides,
  };
}

function meetingRow(
  record: MeetingWithRecord['record'],
  overrides: Partial<MeetingWithRecord> = {},
): MeetingWithRecord {
  return {
    recording_id: 85,
    started_at: '2026-11-23T19:31:00Z',
    has_content: true,
    record,
    history: [],
    ...overrides,
  };
}

/** Route GETs by path so the order of calls does not matter. */
function serve(routes: Record<string, unknown>) {
  get.mockImplementation(async (path: string) => {
    const match = Object.keys(routes).find((key) => path.endsWith(key));
    if (!match) throw new Error(`unexpected GET ${path}`);
    return ok(routes[match]);
  });
}

function asRole(canEdit: boolean) {
  mockedRole.mockReturnValue({ canEdit } as ReturnType<typeof useTenantRole>);
}

beforeEach(() => {
  jest.clearAllMocks();
  asRole(true);
  URL.createObjectURL = jest.fn(() => 'blob:record');
  URL.revokeObjectURL = jest.fn();
});

describe('DocumentsTab', () => {
  describe('the list of meetings', () => {
    it('asks for the session’s meetings and lists them in order', async () => {
      serve({
        '/records/': {
          meetings: [
            meetingRow(summary('ISSUED')),
            meetingRow(null, { recording_id: 91, started_at: '2026-12-02T15:00:00Z' }),
          ],
        },
      });

      render(<DocumentsTab sessionId={SESSION} />);

      const rows = await screen.findAllByRole('listitem');
      expect(get).toHaveBeenCalledWith('/onboarding/sessions/6/records/');
      expect(rows[0]).toHaveTextContent('Meeting 1');
      expect(rows[0]).toHaveTextContent('MR-000085-v1');
      expect(rows[0]).toHaveTextContent('Issued — awaiting signatures');
      expect(rows[1]).toHaveTextContent('Meeting 2');
      expect(rows[1]).toHaveTextContent('No record prepared yet.');
    });

    it('says so when the session has no meetings', async () => {
      serve({ '/records/': { meetings: [] } });

      render(<DocumentsTab sessionId={SESSION} />);

      expect(
        await screen.findByText('No meetings have been recorded in this session yet.'),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /download all meetings/i })).toBeDisabled();
    });

    it('will not prepare a record for a meeting that has not been processed', async () => {
      serve({ '/records/': { meetings: [meetingRow(null, { has_content: false })] } });

      render(<DocumentsTab sessionId={SESSION} />);

      expect(await screen.findByRole('button', { name: 'Prepare record' })).toBeDisabled();
      expect(
        screen.getByText('Process this recording before preparing a record.'),
      ).toBeInTheDocument();
    });

    it('notes earlier versions of a record', async () => {
      serve({
        '/records/': {
          meetings: [
            meetingRow(summary('DRAFT', { id: 12, version: 2, record_number: 'MR-000085-v2' }), {
              history: [summary('VOIDED')],
            }),
          ],
        },
      });

      render(<DocumentsTab sessionId={SESSION} />);

      expect(await screen.findByText('1 earlier version')).toBeInTheDocument();
    });

    it('shows the server’s reason when the list cannot be loaded', async () => {
      get.mockResolvedValue(refused(500, { detail: 'Records are unavailable.' }));

      render(<DocumentsTab sessionId={SESSION} />);

      expect(await screen.findByRole('alert')).toHaveTextContent('Records are unavailable.');
    });
  });

  describe('preparing and reviewing a draft', () => {
    it('prepares a record and shows its content', async () => {
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(ok(detail('DRAFT'), 201));
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      const panel = await screen.findByRole('region', { name: 'Record MR-000085-v1' });
      expect(post).toHaveBeenCalledWith('/onboarding/recordings/85/records/', {});
      expect(within(panel).getByText('Pomodoro Trattoria LLC')).toBeInTheDocument();
      expect(
        within(panel).getByText(/Maria Rossi, Owner \(maria@example.com\)/),
      ).toBeInTheDocument();
      expect(
        within(panel).getByText('Not issued. This draft follows the recording until you issue it.'),
      ).toBeInTheDocument();
    });

    it('numbers the agreements and renders bold without its markers', async () => {
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(ok(detail('DRAFT'), 201));
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      const agreements = within(
        await screen.findByRole('list', { name: 'Agreements' }),
      ).getAllByRole('listitem');
      expect(agreements).toHaveLength(2);
      expect(agreements[0]).toHaveTextContent('A-1Budget split evenly.');
      expect(agreements[0]).not.toHaveTextContent('**');
      expect(within(agreements[0]).getByText('Budget split').tagName).toBe('STRONG');
      expect(agreements[1]).toHaveTextContent('A-2Contract review before launch.');
    });

    it('numbers the transcript lines', async () => {
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(ok(detail('DRAFT'), 201));
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      const lines = within(
        await screen.findByRole('list', { name: 'Transcript' }),
      ).getAllByRole('listitem');
      expect(lines[0]).toHaveTextContent('1Naveen: Shall we split the budget?');
      expect(lines[1]).toHaveTextContent('2Maria Rossi: Yes, agreed.');
    });

    it('says when a meeting recorded no agreements', async () => {
      const empty = detail('DRAFT');
      empty.document.agreements.items = [];
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(ok(empty, 201));
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      expect(
        await screen.findByText('No agreements were recorded in this meeting.'),
      ).toBeInTheDocument();
    });

    it('shows every readiness check with whether it must be fixed', async () => {
      const checks = [
        check('content', true),
        check('party_details', false),
        check('agreements', false, false),
      ];
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(ok(detail('DRAFT', checks), 201));
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      const items = within(
        await screen.findByRole('list', { name: 'Readiness checks' }),
      ).getAllByRole('listitem');
      expect(items).toHaveLength(3);
      expect(within(items[0]).getByLabelText('Passed')).toBeInTheDocument();
      expect(within(items[1]).getByLabelText('Must be fixed')).toBeInTheDocument();
      expect(items[1]).toHaveTextContent('party_details failed');
      expect(within(items[2]).getByLabelText('Note')).toBeInTheDocument();
    });

    it('shows why a record could not be prepared', async () => {
      serve({ '/records/': { meetings: [meetingRow(null)] } });
      post.mockResolvedValue(
        refused(409, { error: 'record_exists', detail: 'MR-000085-v1 is already DRAFT.' }),
      );
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Prepare record' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'MR-000085-v1 is already DRAFT.',
      );
    });
  });

  describe('issuing', () => {
    async function openDraft(readiness: ReadinessItem[] = READY) {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary('DRAFT'))] },
        '/records/11/': detail('DRAFT', readiness),
      });
      const user = userEvent.setup();
      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Open MR-000085-v1' }));
      await screen.findByRole('region', { name: 'Record MR-000085-v1' });
      return user;
    }

    it('asks for confirmation and states that issuing is permanent', async () => {
      const user = await openDraft();

      await user.click(screen.getByRole('button', { name: 'Issue record…' }));

      expect(screen.getByText(/Issuing freezes this record permanently/)).toBeInTheDocument();
      expect(post).not.toHaveBeenCalled();
    });

    it('issues only after the second, explicit step', async () => {
      const user = await openDraft();
      post.mockResolvedValue(ok(detail('ISSUED')));

      await user.click(screen.getByRole('button', { name: 'Issue record…' }));
      await user.click(screen.getByRole('button', { name: 'Issue and freeze' }));

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/issue/', {
          acknowledge_incomplete: false,
        }),
      );
      expect(await screen.findByTestId('fingerprint')).toHaveTextContent(HASH);
      expect(screen.queryByRole('button', { name: 'Issue record…' })).toBeNull();
      expect(screen.queryByRole('list', { name: 'Readiness checks' })).toBeNull();
    });

    it('cancelling leaves the draft unissued', async () => {
      const user = await openDraft();

      await user.click(screen.getByRole('button', { name: 'Issue record…' }));
      await user.click(screen.getByRole('button', { name: 'Cancel' }));

      expect(post).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Issue record…' })).toBeEnabled();
    });

    it('will not start an issue while something must be fixed', async () => {
      await openDraft([check('content', true), check('party_details', false)]);

      expect(screen.getByRole('button', { name: 'Issue record…' })).toBeDisabled();
      expect(screen.getByText('Fix the items marked above before issuing.')).toBeInTheDocument();
    });

    it('a warning alone does not stop an issue', async () => {
      await openDraft([check('content', true), check('agreements', false, false)]);

      expect(screen.getByRole('button', { name: 'Issue record…' })).toBeEnabled();
    });

    it('requires the gap in a transcript to be acknowledged before issuing', async () => {
      const user = await openDraft([check('content', true), check('completeness', false)]);
      post.mockResolvedValue(ok(detail('ISSUED')));

      await user.click(screen.getByRole('button', { name: 'Issue record…' }));
      const confirm = screen.getByRole('button', { name: 'Issue and freeze' });
      expect(confirm).toBeDisabled();

      await user.click(
        screen.getByRole('checkbox', {
          name: /transcript does not cover the whole meeting/i,
        }),
      );
      expect(confirm).toBeEnabled();
      await user.click(confirm);

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/issue/', {
          acknowledge_incomplete: true,
        }),
      );
    });

    it('shows the server’s checks when it refuses to issue', async () => {
      const user = await openDraft();
      post.mockResolvedValue(
        refused(409, {
          error: 'not_ready',
          detail: 'This record is not ready to issue.',
          readiness: [check('content', true), check('unreviewed_details', false)],
        }),
      );

      await user.click(screen.getByRole('button', { name: 'Issue record…' }));
      await user.click(screen.getByRole('button', { name: 'Issue and freeze' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'This record is not ready to issue.',
      );
      expect(screen.getByText('unreviewed_details failed')).toBeInTheDocument();
      expect(screen.queryByTestId('fingerprint')).toBeNull();
    });

    it('discards a draft', async () => {
      const user = await openDraft();
      post.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });

      await user.click(screen.getByRole('button', { name: 'Discard draft' }));

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/discard/', {}),
      );
      await waitFor(() =>
        expect(screen.queryByRole('region', { name: 'Record MR-000085-v1' })).toBeNull(),
      );
    });
  });

  describe('an issued record', () => {
    async function openIssued() {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary('ISSUED'))] },
        '/records/11/': detail('ISSUED'),
      });
      const user = userEvent.setup();
      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Open MR-000085-v1' }));
      await screen.findByRole('region', { name: 'Record MR-000085-v1' });
      return user;
    }

    it('shows its fingerprint and offers no way to issue or discard it', async () => {
      await openIssued();

      expect(screen.getByTestId('fingerprint')).toHaveTextContent(HASH);
      expect(screen.queryByRole('button', { name: 'Issue record…' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Discard draft' })).toBeNull();
    });

    it('will not void without a reason', async () => {
      const user = await openIssued();

      await user.click(screen.getByRole('button', { name: 'Void record…' }));

      expect(screen.getByRole('button', { name: 'Void this record' })).toBeDisabled();
      await user.type(screen.getByLabelText('Reason for voiding'), '   ');
      expect(screen.getByRole('button', { name: 'Void this record' })).toBeDisabled();
      expect(post).not.toHaveBeenCalled();
    });

    it('voids with the reason given and then offers a new version', async () => {
      const user = await openIssued();
      post.mockResolvedValue(
        ok(detail('VOIDED', [], { void_reason: 'Wrong signatory named.' })),
      );

      await user.click(screen.getByRole('button', { name: 'Void record…' }));
      await user.type(screen.getByLabelText('Reason for voiding'), 'Wrong signatory named.');
      await user.click(screen.getByRole('button', { name: 'Void this record' }));

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/void/', {
          reason: 'Wrong signatory named.',
        }),
      );
      expect(await screen.findByText('Voided: Wrong signatory named.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Prepare a new version' })).toBeEnabled();
      expect(screen.queryByRole('button', { name: 'Void record…' })).toBeNull();
    });

    it('keeps a void reason being typed when a PDF is downloaded', async () => {
      const user = await openIssued();
      jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

      await user.click(screen.getByRole('button', { name: 'Void record…' }));
      await user.type(screen.getByLabelText('Reason for voiding'), 'Wrong signatory');
      await user.click(screen.getByRole('button', { name: 'Download MR-000085-v1' }));

      await waitFor(() => expect(get).toHaveBeenCalledWith('/onboarding/records/11/pdf/'));
      expect(screen.getByLabelText('Reason for voiding')).toHaveValue('Wrong signatory');
    });

    it('prepares a new version from a voided record', async () => {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary('VOIDED'))] },
        '/records/11/': detail('VOIDED'),
      });
      post.mockResolvedValue(
        ok(detail('DRAFT', READY, { id: 12, version: 2, record_number: 'MR-000085-v2' }), 201),
      );
      const user = userEvent.setup();
      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Open MR-000085-v1' }));

      await user.click(await screen.findByRole('button', { name: 'Prepare a new version' }));

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/supersede/', {}),
      );
      expect(
        await screen.findByRole('region', { name: 'Record MR-000085-v2' }),
      ).toBeInTheDocument();
    });

    it('lists the record’s history', async () => {
      await openIssued();

      const trail = within(screen.getByRole('list', { name: 'Audit trail' })).getAllByRole(
        'listitem',
      );
      expect(trail).toHaveLength(1);
      expect(trail[0]).toHaveTextContent('Draft prepared · naveen');
    });
  });

  describe('downloads', () => {
    it('downloads one record as a PDF named after it', async () => {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary('ISSUED'))] },
        '/records/11/pdf/': {},
      });
      const clicked: string[] = [];
      jest
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(function (this: HTMLAnchorElement) {
          clicked.push(this.download);
        });
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Download MR-000085-v1' }));

      await waitFor(() => expect(clicked).toEqual(['MR-000085-v1.pdf']));
      expect(get).toHaveBeenCalledWith('/onboarding/records/11/pdf/');
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:record');
    });

    it('downloads every meeting as one binder', async () => {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary('ISSUED'))] },
        '/sessions/6/binder/': {},
      });
      const clicked: string[] = [];
      jest
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(function (this: HTMLAnchorElement) {
          clicked.push(this.download);
        });
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: /download all meetings/i }));

      await waitFor(() => expect(clicked).toEqual(['meeting-records-session-6.pdf']));
      expect(get).toHaveBeenCalledWith('/onboarding/sessions/6/binder/');
    });
  });

  describe('signatories and signing', () => {
    async function open(record: RecordDetail) {
      serve({
        '/sessions/6/records/': { meetings: [meetingRow(summary(record.status))] },
        '/records/11/': record,
      });
      const user = userEvent.setup();
      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Open MR-000085-v1' }));
      await screen.findByRole('region', { name: 'Record MR-000085-v1' });
      return user;
    }

    it('edits who signs a draft and saves the whole list', async () => {
      const user = await open(detail('DRAFT'));
      put.mockResolvedValue(ok(detail('DRAFT')));

      await user.click(screen.getByRole('button', { name: 'Add signatory' }));
      await user.type(screen.getByLabelText('Name of signatory 3'), 'Luca Rossi');
      await user.type(screen.getByLabelText('Email of signatory 3'), 'luca@example.com');
      await user.click(screen.getByRole('button', { name: 'Remove signatory 1' }));
      await user.click(screen.getByRole('button', { name: 'Save signatories' }));

      await waitFor(() =>
        expect(put).toHaveBeenCalledWith('/onboarding/records/11/signatories/', {
          signatories: [
            { party: 'CLIENT', name: 'Maria Rossi', title: 'Owner', email: 'maria@example.com', required: true },
            { party: 'CLIENT', name: 'Luca Rossi', title: '', email: 'luca@example.com', required: true },
          ],
        }),
      );
    });

    it('shows the server’s reason when the list is refused', async () => {
      const user = await open(detail('DRAFT'));
      put.mockResolvedValue(
        refused(400, { error: 'invalid_signatories', detail: 'luca@ is not a valid email address.' }),
      );

      await user.click(screen.getByRole('button', { name: 'Save signatories' }));

      expect(await screen.findByRole('alert')).toHaveTextContent('luca@ is not a valid email address.');
    });

    it('shows each person’s progress, remarks and evidence once issued', async () => {
      await open(
        detail('PARTIALLY_SIGNED', [], {
          signatories: [
            signatory({ id: 1, party: 'AGENCY', party_name: 'Zorven Agency', name: 'Naveen H', email: 'naveen@agency.test', link_expires_at: '2026-12-09T10:00:00Z' }),
            signatory({
              status: 'SIGNED',
              signed_at: '2026-11-26T10:00:00Z',
              typed_name: 'Maria Rossi',
              method: 'EMAIL_CODE',
              ip_address: '203.0.113.7',
              remarks: 'Item 2: legal review budget only.',
            }),
          ],
        }),
      );

      const people = within(screen.getByRole('list', { name: 'Signatories' })).getAllByRole('listitem');
      expect(people[0]).toHaveTextContent('Awaiting signature');
      expect(people[0]).toHaveTextContent('Link valid until');
      expect(people[1]).toHaveTextContent('emailed link and one-time code · from 203.0.113.7');
      expect(people[1]).toHaveTextContent('Remarks: Item 2: legal review budget only.');
      expect(screen.queryByRole('form', { name: 'Your signature' })).toBeNull();
    });

    it('resends links and says the old ones stop working', async () => {
      const user = await open(detail('ISSUED'));
      post.mockResolvedValue(ok({ ...detail('ISSUED'), sent: 2 }));

      await user.click(screen.getByRole('button', { name: 'Send reminder' }));

      await waitFor(() => expect(post).toHaveBeenCalledWith('/onboarding/records/11/remind/', {}));
      expect(await screen.findByRole('status')).toHaveTextContent(
        'Sent 2 new signing links. Earlier links no longer work.',
      );
    });

    it('lets the agency signatory sign, with consent and the fingerprint shown', async () => {
      const user = await open(detail('ISSUED', [], { you: 1 }));
      post.mockResolvedValue(ok(detail('PARTIALLY_SIGNED')));
      const form = screen.getByRole('form', { name: 'Your signature' });
      const button = within(form).getByRole('button', { name: 'Sign record' });

      expect(button).toBeDisabled();
      await user.click(within(form).getByRole('checkbox'));
      await user.click(button);

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/sign/', {
          content_hash: HASH,
          action: 'sign',
          typed_name: 'Naveen H',
          consent: true,
        }),
      );
    });

    it('declines only with a reason', async () => {
      const user = await open(detail('ISSUED', [], { you: 1 }));
      post.mockResolvedValue(ok(detail('DECLINED')));
      const form = screen.getByRole('form', { name: 'Your signature' });

      await user.click(within(form).getByText('Decline'));
      const button = within(form).getByRole('button', { name: 'Decline to sign' });
      expect(button).toBeDisabled();
      await user.type(within(form).getByLabelText('Reason for declining'), 'Wrong budget.');
      await user.click(button);

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/sign/', {
          content_hash: HASH,
          action: 'decline',
          reason: 'Wrong budget.',
        }),
      );
    });

    it('asks an agency signer to acknowledge remarks made after they signed', async () => {
      const user = await open(
        detail('PARTIALLY_SIGNED', [], {
          you: 1,
          signatories: [
            signatory({ id: 1, party: 'AGENCY', name: 'Naveen H', email: 'naveen@agency.test', status: 'SIGNED', signed_at: '2026-11-26T09:00:00Z' }),
            signatory({ status: 'SIGNED', signed_at: '2026-11-26T10:00:00Z', remarks: 'A remark.' }),
          ],
          remarks_to_acknowledge: { '1': ['Maria Rossi'] },
        }),
      );
      post.mockResolvedValue(ok(detail('COMPLETED')));

      expect(screen.queryByRole('form', { name: 'Your signature' })).toBeNull();
      await user.click(screen.getByRole('button', { name: 'I have read the remarks' }));

      await waitFor(() =>
        expect(post).toHaveBeenCalledWith('/onboarding/records/11/sign/', {
          content_hash: HASH,
          action: 'acknowledge_remarks',
        }),
      );
    });

    it('lets a viewer who is a signatory sign, but not edit or remind', async () => {
      asRole(false);
      await open(detail('ISSUED', [], { you: 1 }));

      expect(screen.getByRole('form', { name: 'Your signature' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Send reminder' })).toBeNull();
    });
  });

  describe('a viewer', () => {
    it('can open and download but is offered no changes', async () => {
      asRole(false);
      serve({
        '/sessions/6/records/': {
          meetings: [
            meetingRow(summary('DRAFT')),
            meetingRow(null, { recording_id: 91 }),
          ],
        },
        '/records/11/': detail('DRAFT'),
      });
      const user = userEvent.setup();

      render(<DocumentsTab sessionId={SESSION} />);
      await user.click(await screen.findByRole('button', { name: 'Open MR-000085-v1' }));
      await screen.findByRole('region', { name: 'Record MR-000085-v1' });

      expect(screen.getByRole('button', { name: 'Download MR-000085-v1' })).toBeEnabled();
      expect(screen.queryByRole('button', { name: 'Prepare record' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Issue record…' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Discard draft' })).toBeNull();
      expect(screen.getByRole('list', { name: 'Readiness checks' })).toBeInTheDocument();
    });
  });
});
