import { render, screen, waitFor } from '@testing-library/react'
import MeetingEvidence from '@/components/onboarding/MeetingEvidence'
import type {
  RecordingItem,
  CapturedMedia,
  ConsentState,
} from '@/lib/onboarding-sessions'

const mockListSessionRecordings = jest.fn()
const mockListSessionCaptures = jest.fn()
const mockGetSessionDetail = jest.fn()

jest.mock('@/lib/onboarding-sessions', () => ({
  listSessionRecordings: (...args: unknown[]) =>
    mockListSessionRecordings(...args),
  listSessionCaptures: (...args: unknown[]) =>
    mockListSessionCaptures(...args),
  getSessionDetail: (...args: unknown[]) => mockGetSessionDetail(...args),
}))

function recording(
  overrides: Partial<RecordingItem> = {},
): RecordingItem {
  return {
    id: 'rec-1',
    session: 'sess-1',
    modality: 'AUDIO',
    status: 'SUMMARIZED',
    duration_s: 95,
    audio_asset: 'asset-1',
    has_transcript: true,
    has_summary: true,
    started_at: '2026-08-15T10:00:00Z',
    stopped_at: '2026-08-15T10:01:35Z',
    ...overrides,
  }
}

function capture(
  overrides: Partial<CapturedMedia> = {},
): CapturedMedia {
  return {
    id: 'cap-1',
    file_name: 'whiteboard.jpg',
    file_type: 'image',
    file_size: 2048,
    uploaded_at: '2026-08-15T10:00:00Z',
    usage_tag: 'business_photo',
    ...overrides,
  }
}

const GRANTED_CONSENT: ConsentState = {
  granted: true,
  granted_at: '2026-08-14T10:00:00Z',
  method: 'VERBAL_RECORDED',
  scope: { audio: true, transcript: true, captured_media: true },
}

const NO_CONSENT: ConsentState = {
  granted: false,
  granted_at: null,
  method: null,
  scope: null,
}

function setupMocks(opts: {
  recordings?: RecordingItem[]
  captures?: CapturedMedia[]
  consent?: ConsentState
}) {
  mockListSessionRecordings.mockResolvedValue(opts.recordings ?? [])
  mockListSessionCaptures.mockResolvedValue(opts.captures ?? [])
  mockGetSessionDetail.mockResolvedValue({
    id: 'sess-1',
    company: 'co-1',
    status: 'REVIEW_PENDING',
    questionnaire: null,
    created_at: '2026-08-15T10:00:00Z',
    updated_at: '2026-08-15T10:00:00Z',
    legal_next_states: [],
    evidence_manifest_hash: '',
    process_job_id: '',
    process_summary: {},
    consent: opts.consent ?? NO_CONSENT,
  })
}

describe('MeetingEvidence', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders recordings with duration and summary link (AC-1)', async () => {
    setupMocks({
      recordings: [recording()],
      consent: GRANTED_CONSENT,
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('evidence-recordings')).toBeInTheDocument()
    })

    expect(screen.getByText('1:35')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()

    const link = screen.getByText('View summary')
    expect(link).toHaveAttribute(
      'href',
      '/onboarding/sessions/sess-1?recording=rec-1',
    )
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('hides summary link when has_summary is false (AC-1)', async () => {
    setupMocks({
      recordings: [recording({ has_summary: false })],
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('evidence-recordings')).toBeInTheDocument()
    })

    expect(screen.queryByText('View summary')).not.toBeInTheDocument()
  })

  it('renders captures with usage_tag badge (AC-1)', async () => {
    setupMocks({
      captures: [capture({ usage_tag: 'brand_asset' })],
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('evidence-captures')).toBeInTheDocument()
    })

    expect(screen.getByText('whiteboard.jpg')).toBeInTheDocument()
    expect(screen.getByText('brand asset')).toBeInTheDocument()
  })

  it('renders video icon for video captures', async () => {
    setupMocks({
      captures: [capture({ file_type: 'video', file_name: 'demo.mp4' })],
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByText('demo.mp4')).toBeInTheDocument()
    })
  })

  it('returns null when no recordings and no captures (AC-2)', async () => {
    setupMocks({ recordings: [], captures: [] })

    const { container } = render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(mockListSessionRecordings).toHaveBeenCalled()
    })

    await waitFor(() => {
      expect(container.querySelector('[data-testid="meeting-evidence"]')).toBeNull()
      expect(container.querySelector('[data-testid="meeting-evidence-loading"]')).toBeNull()
    })
  })

  it('shows consent method and date when granted (AC-3)', async () => {
    setupMocks({
      recordings: [recording()],
      consent: GRANTED_CONSENT,
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('consent-reference')).toBeInTheDocument()
    })

    expect(screen.getByText(/Verbal \(recorded\)/)).toBeInTheDocument()
    expect(screen.getByText(/Aug/)).toBeInTheDocument()
    expect(screen.getByText(/2026/)).toBeInTheDocument()
  })

  it('shows written consent label for CHECKBOX method (AC-3)', async () => {
    setupMocks({
      recordings: [recording()],
      consent: {
        ...GRANTED_CONSENT,
        method: 'CHECKBOX',
      },
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByText(/Written consent/)).toBeInTheDocument()
    })
  })

  it('hides consent section when not granted (AC-3)', async () => {
    setupMocks({
      recordings: [recording()],
      consent: NO_CONSENT,
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('meeting-evidence')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('consent-reference')).not.toBeInTheDocument()
  })

  it('does not expose subject details in consent reference (AC-3)', async () => {
    setupMocks({
      recordings: [recording()],
      consent: GRANTED_CONSENT,
    })

    render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('consent-reference')).toBeInTheDocument()
    })

    expect(screen.queryByText(/subject/i)).not.toBeInTheDocument()
  })

  it('returns null on API error', async () => {
    mockListSessionRecordings.mockRejectedValue(new Error('Network error'))
    mockListSessionCaptures.mockRejectedValue(new Error('Network error'))
    mockGetSessionDetail.mockRejectedValue(new Error('Network error'))

    const { container } = render(<MeetingEvidence sessionId="sess-1" />)

    await waitFor(() => {
      expect(container.querySelector('[data-testid="meeting-evidence"]')).toBeNull()
      expect(container.querySelector('[data-testid="meeting-evidence-loading"]')).toBeNull()
    })
  })

  it('shows loading spinner while fetching', () => {
    mockListSessionRecordings.mockReturnValue(new Promise(() => {}))
    mockListSessionCaptures.mockReturnValue(new Promise(() => {}))
    mockGetSessionDetail.mockReturnValue(new Promise(() => {}))

    render(<MeetingEvidence sessionId="sess-1" />)

    expect(
      screen.getByTestId('meeting-evidence-loading'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Loading meeting evidence/)).toBeInTheDocument()
  })

  it('fetches data for the correct sessionId', async () => {
    setupMocks({ recordings: [recording()] })

    render(<MeetingEvidence sessionId="sess-42" />)

    await waitFor(() => {
      expect(mockListSessionRecordings).toHaveBeenCalledWith('sess-42')
      expect(mockListSessionCaptures).toHaveBeenCalledWith('sess-42')
      expect(mockGetSessionDetail).toHaveBeenCalledWith('sess-42')
    })
  })
})
