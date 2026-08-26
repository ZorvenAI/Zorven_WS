/**
 * K-01 — KeyFindingsReview component tests.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import KeyFindingsReview from '@/components/onboarding/KeyFindingsReview';
import type {
  FieldProvenanceRow,
  ProcessSummary,
  ProvenanceGroup,
  SessionDetail,
  RecordingItem,
  RecordingDetail,
} from '@/lib/onboarding-sessions';

beforeAll(() => {
  Element.prototype.scrollIntoView = jest.fn();
});

jest.mock('next/navigation', () => ({
  useParams: () => ({ sessionId: 'sess-1' }),
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({}),
}));

jest.mock('@/lib/onboarding-sessions', () => ({
  getSessionDetail: jest.fn(),
  getSessionProvenance: jest.fn(),
  listSessionRecordings: jest.fn(),
  getRecordingDetail: jest.fn(),
  getRecordingTranscript: jest.fn(),
  formatTime: (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  },
}));

const mockApi = jest.requireMock('@/lib/onboarding-sessions');

function makeRow(overrides: Partial<FieldProvenanceRow> = {}): FieldProvenanceRow {
  return {
    id: 1,
    session: 1,
    model_name: 'Company',
    field_name: 'company_name',
    extracted_value: 'Acme Corp',
    final_value: null,
    classification: 'KEY',
    confidence: 0.92,
    source_recording: 10,
    source_span: { recording_id: '10', t_start: 12.5, t_end: 18.0 },
    source_media: null,
    status: 'PENDING',
    reviewed_by: null,
    reviewed_at: null,
    wizard_page: 1,
    wizard_page_label: 'Company Info',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...overrides,
  };
}

const baseSummary: ProcessSummary = {
  fields_written: 34,
  conflicts: [],
  dropped_ungrounded: 6,
  coverage: { WF1: 0.94, WF2: 0.88, WF3: 1.0 },
  generated: ['brand_strategy', 'brand_identity'],
};

function makeSession(overrides: Partial<ProcessSummary> = {}): SessionDetail {
  return {
    id: 'sess-1',
    company: 'comp-1',
    status: 'REVIEW_PENDING',
    questionnaire: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    legal_next_states: ['CONFIRMED'],
    evidence_manifest_hash: '',
    process_job_id: 'job-1',
    process_summary: { ...baseSummary, ...overrides } as Record<string, unknown>,
    consent: { granted: true, granted_at: null, method: null, scope: null },
  };
}

function makeGroups(rows: FieldProvenanceRow[]): { session: number; groups: ProvenanceGroup[] } {
  const buckets: Record<number, FieldProvenanceRow[]> = {};
  for (const r of rows) {
    const p = r.wizard_page ?? -1;
    (buckets[p] ??= []).push(r);
  }
  return {
    session: 1,
    groups: Object.entries(buckets).map(([p, fields]) => ({
      page: Number(p),
      label: fields[0]?.wizard_page_label ?? 'Unmapped',
      fields,
    })),
  };
}

function setupMocks(
  summary: Partial<ProcessSummary> = {},
  rows: FieldProvenanceRow[] = [makeRow()],
  recordings: RecordingItem[] = [],
) {
  mockApi.getSessionDetail.mockResolvedValue(makeSession(summary));
  mockApi.getSessionProvenance.mockResolvedValue(makeGroups(rows));
  mockApi.listSessionRecordings.mockResolvedValue(recordings);
  mockApi.getRecordingDetail.mockResolvedValue({
    id: '1',
    session: 'sess-1',
    modality: 'AUDIO',
    status: 'SUMMARIZED',
    duration_s: 120,
    audio_asset: null,
    has_transcript: true,
    has_summary: true,
    started_at: '2026-08-01T00:00:00Z',
    stopped_at: '2026-08-01T00:02:00Z',
    summary: { text: 'Test summary', key_moments: [] },
  } as RecordingDetail);
  mockApi.getRecordingTranscript.mockResolvedValue([
    { text: 'Hello', speaker: 0, t_start: 0, t_end: 2, redaction_applied: false },
  ]);
}

beforeEach(() => {
  jest.clearAllMocks();
});

it('renders summary bar with fields_written and dropped_ungrounded', async () => {
  setupMocks();
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByTestId('summary-bar')).toBeInTheDocument();
  });
  expect(screen.getByTestId('dropped-count')).toHaveTextContent('6');
  expect(screen.getByText('34')).toBeInTheDocument();
});

it('shows conflicts section above provenance groups (AC-4)', async () => {
  const conflictRow = makeRow({
    id: 99,
    field_name: 'industry',
    status: 'CONFLICT',
    classification: 'KEY',
  });
  const normalRow = makeRow({ id: 100, field_name: 'company_name' });
  setupMocks(
    { conflicts: [{ field_name: 'industry', existing_status: 'CONFIRMED' }] },
    [conflictRow, normalRow],
  );

  const { container } = render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByTestId('conflicts-section')).toBeInTheDocument();
  });

  const conflictsSection = container.querySelector('[data-testid="conflicts-section"]');
  const keyFields = container.querySelector('[data-testid="key-fields"]');
  expect(conflictsSection).toBeTruthy();
  expect(keyFields).toBeTruthy();

  const all = Array.from(container.querySelectorAll('[data-testid]'));
  const conflictsIdx = all.indexOf(conflictsSection!);
  const keyIdx = all.indexOf(keyFields!);
  expect(conflictsIdx).toBeLessThan(keyIdx);
});

it('renders dropped_ungrounded count visibly (AC-1)', async () => {
  setupMocks({ dropped_ungrounded: 12 });
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByTestId('dropped-count')).toHaveTextContent('12');
  });
});

it('opens provenance drawer when source indicator is clicked (AC-2)', async () => {
  setupMocks();
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByText('Company Name')).toBeInTheDocument();
  });

  const viewSourceBtn = screen.getByLabelText(/View source for Company Name/);
  fireEvent.click(viewSourceBtn);

  await waitFor(() => {
    expect(screen.getByRole('dialog', { name: /Source evidence/ })).toBeInTheDocument();
  });
});

it('renders KEY fields prominently (not collapsed)', async () => {
  setupMocks({}, [makeRow({ classification: 'KEY', field_name: 'brand_voice' })]);
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByText('Brand Voice')).toBeInTheDocument();
  });
  expect(screen.getByText('Acme Corp')).toBeInTheDocument();
});

it('renders SECONDARY fields collapsed by default', async () => {
  const sec = makeRow({
    id: 2,
    classification: 'SECONDARY',
    field_name: 'phone_number',
    extracted_value: '555-1234',
  });
  setupMocks({}, [makeRow(), sec]);
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByText(/Auto-filled fields/)).toBeInTheDocument();
  });
  expect(screen.queryByText('555-1234')).not.toBeInTheDocument();

  fireEvent.click(screen.getByText(/Auto-filled fields/));
  expect(screen.getByText('555-1234')).toBeInTheDocument();
});

it('shows coverage shortfall with consequences (AC-3)', async () => {
  setupMocks({ coverage: { WF1: 0.5, WF2: 1.0, WF3: 0.3 } });
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByTestId('coverage-section')).toBeInTheDocument();
  });
  expect(screen.getByText(/Discovery & Research/)).toBeInTheDocument();
  expect(screen.getByText(/50% covered/)).toBeInTheDocument();
  expect(screen.getByText(/Schedule follow-up/)).toBeInTheDocument();
});

it('shows generated items list', async () => {
  setupMocks({ generated: ['brand_strategy', 'brand_identity'] });
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByTestId('generated-list')).toHaveTextContent(
      'brand strategy, brand identity',
    );
  });
});

it('shows recording summaries when available', async () => {
  const rec: RecordingItem = {
    id: 'rec-1',
    session: 'sess-1',
    modality: 'AUDIO',
    status: 'SUMMARIZED' as RecordingItem['status'],
    duration_s: 120,
    audio_asset: null,
    has_transcript: true,
    has_summary: true,
    started_at: '2026-08-01T00:00:00Z',
    stopped_at: '2026-08-01T00:02:00Z',
  };
  setupMocks({}, [makeRow()], [rec]);
  render(<KeyFindingsReview sessionId="sess-1" />);
  await waitFor(() => {
    expect(screen.getByText('Test summary')).toBeInTheDocument();
  });
});
