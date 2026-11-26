/**
 * Signed meeting records · step 3 — the public signing page.
 *
 * Only `fetch` is stubbed, so `record-signing.ts` runs for real: these tests
 * cover the page and its client together, including the paths, headers and
 * bodies sent.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import SignRecordPage from '@/app/sign/[token]/page';

jest.mock('next/navigation', () => ({
  useParams: () => ({ token: 'tok-123' }),
}));

const HASH = 'ab12'.repeat(16);

const OVERVIEW = {
  record_number: 'MR-000085-v1',
  status: 'ISSUED',
  agency: 'Zorven Agency',
  client: 'Pomodoro Trattoria LLC',
  meeting_started_at: '2026-11-20T15:00:00Z',
  expires_at: '2026-12-10T15:00:00Z',
  signatory: {
    name: 'Maria Rossi',
    party_name: 'Pomodoro Trattoria LLC',
    status: 'PENDING',
    email_hint: 'm•••a@example.com',
  },
};

const DOCUMENT = {
  record: { number: 'MR-000085-v1', version: 1, supersedes: null },
  clause: { version: '2026-11-draft-1', text: 'This record is evidence of the meeting.' },
  parties: {
    agency: { name: 'Zorven Agency' },
    client: {
      name: 'Pomodoro',
      legal_name: 'Pomodoro Trattoria LLC',
      registered_address: '14 Main Street, Austin',
      signatory_name: 'Maria Rossi',
      signatory_title: 'Owner',
      signatory_email: 'maria@example.com',
      registration_number: '',
    },
  },
  meeting: { recording_id: 85, started_at: '2026-11-20T15:00:00Z', stopped_at: null, duration_s: 600 },
  attendees: [{ name: 'Maria Rossi', role: 'Owner' }],
  consent: null,
  completeness: { state: 'complete', missing_s: 0, note: '' },
  agreements: { preamble: '', items: [{ number: '1', text: 'Launch budget split evenly.' }] },
  description: 'A planning meeting.',
  transcript: ['Naveen: Split evenly?', 'Maria Rossi: Yes, agreed.'],
};

const OPENED = {
  ...OVERVIEW,
  session: 'sess-xyz',
  content_hash: HASH,
  document: DOCUMENT,
  signatories: [
    {
      id: 1,
      party_name: 'Zorven Agency',
      name: 'Naveen H',
      title: '',
      required: true,
      status: 'PENDING',
      signed_at: null,
      remarks: '',
      decline_reason: '',
    },
  ],
  consent: { version: '2026-11-draft-1', text: 'I agree to sign this document electronically.' },
  can_sign: true,
  remarks_to_acknowledge: [] as string[],
};

const fetchMock = jest.fn();

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body });
}

function call(index: number) {
  const [url, init] = fetchMock.mock.calls[index] as [string, RequestInit | undefined];
  return {
    url,
    method: init?.method ?? 'GET',
    headers: (init?.headers ?? {}) as Record<string, string>,
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});

async function openRecord() {
  fetchMock
    .mockImplementationOnce(() => reply(200, OVERVIEW))
    .mockImplementationOnce(() => reply(200, { sent_to: 'm•••a@example.com' }))
    .mockImplementationOnce(() => reply(200, OPENED));
  const user = userEvent.setup();
  render(<SignRecordPage />);
  await user.click(await screen.findByRole('button', { name: /email me a code/i }));
  await user.type(await screen.findByLabelText(/one-time code/i), '123456');
  await user.click(screen.getByRole('button', { name: /open the record/i }));
  await screen.findByText('Launch budget split evenly.');
  return user;
}

describe('before the code', () => {
  it('shows who the record is for, but none of its content', async () => {
    fetchMock.mockImplementationOnce(() => reply(200, OVERVIEW));
    render(<SignRecordPage />);

    expect(await screen.findByText(/Meeting record MR-000085-v1/)).toBeInTheDocument();
    expect(screen.getByText('m•••a@example.com')).toBeInTheDocument();
    expect(screen.queryByText(/Launch budget/)).not.toBeInTheDocument();
    expect(call(0).url).toMatch(/\/onboarding\/public\/records\/sign\/tok-123\/$/);
    expect(call(0).headers).not.toHaveProperty('Authorization');
  });

  it('says plainly that a bad link cannot be used', async () => {
    fetchMock.mockImplementationOnce(() =>
      reply(404, { error: 'link_invalid', detail: 'This link is not valid.' }),
    );
    render(<SignRecordPage />);

    expect(await screen.findByText('This link cannot be used')).toBeInTheDocument();
  });

  it('does not offer a code on a closed record', async () => {
    fetchMock.mockImplementationOnce(() => reply(200, { ...OVERVIEW, status: 'VOIDED' }));
    render(<SignRecordPage />);

    expect(await screen.findByText(/withdrawn by the sender/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /email me a code/i })).not.toBeInTheDocument();
  });

  it('reports a wrong code and stays on the code step', async () => {
    fetchMock
      .mockImplementationOnce(() => reply(200, OVERVIEW))
      .mockImplementationOnce(() => reply(200, { sent_to: 'm•••a@example.com' }))
      .mockImplementationOnce(() =>
        reply(400, { error: 'code_incorrect', detail: 'That code is not right.' }),
      );
    const user = userEvent.setup();
    render(<SignRecordPage />);
    await user.click(await screen.findByRole('button', { name: /email me a code/i }));
    await user.type(await screen.findByLabelText(/one-time code/i), '000000');
    await user.click(screen.getByRole('button', { name: /open the record/i }));

    expect(await screen.findByText('That code is not right.')).toBeInTheDocument();
    expect(call(2).body).toEqual({ code: '000000' });
    expect(screen.queryByText(/Launch budget/)).not.toBeInTheDocument();
  });
});

describe('reading and signing', () => {
  it('shows the whole record once the code is right', async () => {
    await openRecord();

    expect(screen.getByText('A planning meeting.')).toBeInTheDocument();
    expect(screen.getByText('Maria Rossi: Yes, agreed.')).toBeInTheDocument();
    expect(screen.getByText('This record is evidence of the meeting.')).toBeInTheDocument();
    expect(screen.getByText('Naveen H')).toBeInTheDocument();
  });

  it('signs with the session and the fingerprint the signer was shown', async () => {
    const user = await openRecord();
    fetchMock.mockImplementationOnce(() =>
      reply(200, {
        ...OPENED,
        status: 'PARTIALLY_SIGNED',
        signatory: { ...OVERVIEW.signatory, status: 'SIGNED' },
        can_sign: false,
      }),
    );

    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /^sign$/i }));

    expect(await screen.findByText('Thank you')).toBeInTheDocument();
    const sent = call(3);
    expect(sent.url).toMatch(/\/tok-123\/submit\/$/);
    expect(sent.headers['X-Signing-Session']).toBe('sess-xyz');
    expect(sent.body).toEqual({
      content_hash: HASH,
      action: 'sign',
      typed_name: 'Maria Rossi',
      consent: true,
    });
  });

  it('will not sign without consent', async () => {
    const user = await openRecord();

    await user.click(screen.getByRole('button', { name: /^sign$/i }));

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('declines with a reason', async () => {
    const user = await openRecord();
    fetchMock.mockImplementationOnce(() =>
      reply(200, {
        ...OPENED,
        status: 'DECLINED',
        signatory: { ...OVERVIEW.signatory, status: 'DECLINED' },
        can_sign: false,
      }),
    );

    await user.click(screen.getByText('Decline'));
    await user.type(screen.getByLabelText(/why are you declining/i), 'Budget is wrong.');
    await user.click(screen.getByRole('button', { name: /decline to sign/i }));

    expect(await screen.findByText('You declined this record')).toBeInTheDocument();
    expect(call(3).body).toEqual({
      content_hash: HASH,
      action: 'decline',
      reason: 'Budget is wrong.',
    });
  });

  it('sends a signer back to the code step when the session has lapsed', async () => {
    const user = await openRecord();
    fetchMock.mockImplementationOnce(() =>
      reply(401, { error: 'session_expired', detail: 'Confirm your email with a new code.' }),
    );

    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: /^sign$/i }));

    expect(await screen.findByText('Confirm your email with a new code.')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /email me a code/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Launch budget/)).not.toBeInTheDocument();
  });

  it('asks an earlier signer to acknowledge new remarks', async () => {
    fetchMock
      .mockImplementationOnce(() =>
        reply(200, { ...OVERVIEW, signatory: { ...OVERVIEW.signatory, status: 'SIGNED' } }),
      )
      .mockImplementationOnce(() => reply(200, { sent_to: 'm•••a@example.com' }))
      .mockImplementationOnce(() =>
        reply(200, {
          ...OPENED,
          signatory: { ...OVERVIEW.signatory, status: 'SIGNED' },
          can_sign: false,
          remarks_to_acknowledge: ['Naveen H'],
        }),
      )
      .mockImplementationOnce(() =>
        reply(200, { ...OPENED, status: 'COMPLETED', can_sign: false }),
      );
    const user = userEvent.setup();
    render(<SignRecordPage />);
    await user.click(await screen.findByRole('button', { name: /email me a code/i }));
    await user.type(await screen.findByLabelText(/one-time code/i), '123456');
    await user.click(screen.getByRole('button', { name: /open the record/i }));

    await user.click(await screen.findByRole('button', { name: /i have read the remarks/i }));

    expect(screen.queryByRole('button', { name: /^sign$/i })).not.toBeInTheDocument();
    expect(call(3).body).toEqual({ content_hash: HASH, action: 'acknowledge_remarks' });
    expect(await screen.findByText(/Everyone required has signed/)).toBeInTheDocument();
  });
});
