import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { OnboardingReview } from '@/components/onboarding/OnboardingReview'
import { apiClient } from '@/lib/api'

jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
  },
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}))

jest.mock('@/components/onboarding/MeetingEvidence', () => ({
  __esModule: true,
  default: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="meeting-evidence">Evidence for {sessionId}</div>
  ),
}))

const COMPANY = {
  id: 123,
  name: 'Test Corp',
  industry: 'technology',
  description: 'A test company',
  brand_voice: 'professional',
  vision_statement: '',
  mission_statement: '',
  values: '',
  positioning_statement: '',
}

describe('OnboardingReview', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    localStorage.setItem('company_id', '123')
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => COMPANY,
    })
  })

  it('renders MeetingEvidence when sessionId is provided (AC-1)', async () => {
    render(<OnboardingReview sessionId="sess-1" />)

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    expect(screen.getByTestId('meeting-evidence')).toBeInTheDocument()
    expect(screen.getByText('Evidence for sess-1')).toBeInTheDocument()
  })

  it('does not render MeetingEvidence when sessionId is null (AC-2)', async () => {
    render(<OnboardingReview sessionId={null} />)

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('meeting-evidence')).not.toBeInTheDocument()
  })

  it('does not render MeetingEvidence when sessionId is omitted (AC-2)', async () => {
    render(<OnboardingReview />)

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('meeting-evidence')).not.toBeInTheDocument()
  })

  it('Back button includes sessionId in URL when present', async () => {
    render(<OnboardingReview sessionId="sess-back" />)

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(mockPush).toHaveBeenCalledWith(
      '/onboarding/step-4?sessionId=sess-back',
    )
  })

  it('Back button omits sessionId when absent', async () => {
    render(<OnboardingReview />)

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(mockPush).toHaveBeenCalledWith('/onboarding/step-4')
  })

  it('renders company data sections', async () => {
    render(<OnboardingReview />)

    await waitFor(() => {
      expect(screen.getByText('Company Information')).toBeInTheDocument()
    })

    expect(screen.getByText('Test Corp')).toBeInTheDocument()
    expect(screen.getByText('technology')).toBeInTheDocument()
    expect(screen.getByText('A test company')).toBeInTheDocument()
  })
})
