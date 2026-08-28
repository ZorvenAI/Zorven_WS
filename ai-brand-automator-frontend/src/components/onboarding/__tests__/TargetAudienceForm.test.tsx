import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TargetAudienceForm } from '@/components/onboarding/TargetAudienceForm'
import { apiClient } from '@/lib/api'

jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    patch: jest.fn(),
  },
}))

const mockPush = jest.fn()
let mockSessionId: string | null = null
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
  useSearchParams: () => ({
    get: (key: string) => (key === 'sessionId' ? mockSessionId : null),
  }),
}))

const mockGetSessionProvenance = jest.fn()
const mockEditProvenance = jest.fn()
jest.mock('@/lib/onboarding-sessions', () => ({
  getSessionProvenance: (...args: unknown[]) =>
    mockGetSessionProvenance(...args),
  editProvenance: (...args: unknown[]) => mockEditProvenance(...args),
}))

describe('TargetAudienceForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
    window.localStorage.clear()
    localStorage.setItem('company_id', '123')
    localStorage.setItem('access_token', 'test-token')
    mockSessionId = null
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    })
  })

  it('renders all target audience fields including K-03 fields', () => {
    render(<TargetAudienceForm />)

    expect(screen.getByLabelText(/target audience/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/demographics/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/psychographics/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/pain points/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/desired outcomes/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/audience languages/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/customer proof/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<TargetAudienceForm />)

    const targetAudienceInput = screen.getByLabelText(
      /primary target audience/i
    )
    const painPointsInput = screen.getByLabelText(/key pain points/i)
    const desiredOutcomesInput = screen.getByLabelText(/desired outcomes/i)

    expect(targetAudienceInput).toBeRequired()
    expect(painPointsInput).toBeRequired()
    expect(desiredOutcomesInput).toBeRequired()

    const demographicsInput = screen.getByLabelText(/^demographics$/i)
    const psychographicsInput = screen.getByLabelText(/^psychographics$/i)
    expect(demographicsInput).not.toBeRequired()
    expect(psychographicsInput).not.toBeRequired()
  })

  it('submits form with audience_languages serialized as JSON array', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Small business owners' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Limited time' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Better productivity' },
    })
    fireEvent.change(screen.getByLabelText(/audience languages/i), {
      target: { value: 'en-IN, kn-IN, hi-IN' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        '/companies/123/',
        expect.objectContaining({
          target_audience: 'Small business owners',
          audience_languages: ['en-IN', 'kn-IN', 'hi-IN'],
        })
      )
    })
  })

  it('submits form with customer_proof serialized as testimonial array', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'SMBs' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Cost' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Savings' },
    })
    fireEvent.change(screen.getByLabelText(/customer proof/i), {
      target: { value: 'Great product!\nSaved us time' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        '/companies/123/',
        expect.objectContaining({
          customer_proof: [
            { type: 'testimonial', text: 'Great product!' },
            { type: 'testimonial', text: 'Saved us time' },
          ],
        })
      )
    })
  })

  it('sends null for empty audience_languages', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'SMBs' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Cost' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Savings' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      const callArgs = (apiClient.patch as jest.Mock).mock.calls[0][1]
      expect(callArgs.audience_languages).toBeNull()
      expect(callArgs.customer_proof).toBeNull()
    })
  })

  it('navigates after successful submission', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Test audience' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Test pain points' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Test outcomes' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/onboarding/step-4')
    })
  })

  it('handles submission errors gracefully', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({
        message: 'Invalid data provided',
      }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Test' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Test pain' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Test outcomes' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid data provided')).toBeInTheDocument()
    })

    expect(mockPush).not.toHaveBeenCalled()
  })

  it('disables submit button while loading', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => setTimeout(() => resolve(mockResponse), 100))
    )

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Target' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Pain' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Outcomes' },
    })

    const submitButton = screen.getByRole('button', { name: /next step/i })
    fireEvent.click(submitButton)

    expect(submitButton).toBeDisabled()

    await waitFor(
      () => {
        expect(mockPush).toHaveBeenCalledWith('/onboarding/step-4')
      },
      { timeout: 3000 }
    )
  })

  it('loads and displays existing audience_languages from API', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 123,
            name: 'Test',
            audience_languages: ['en-IN', 'kn-IN'],
            customer_proof: [
              { type: 'testimonial', text: 'Excellent service' },
            ],
          },
        ],
      }),
    })

    render(<TargetAudienceForm />)

    await waitFor(() => {
      expect(screen.getByLabelText(/audience languages/i)).toHaveValue(
        'en-IN, kn-IN'
      )
    })

    await waitFor(() => {
      expect(screen.getByLabelText(/customer proof/i)).toHaveValue(
        'Excellent service'
      )
    })
  })

  it('works without sessionId — no provenance fetch (AC-2)', async () => {
    mockSessionId = null
    ;(apiClient.patch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 123 }),
    })

    render(<TargetAudienceForm />)

    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Manual audience' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Pain' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Goals' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalled()
    })

    expect(mockGetSessionProvenance).not.toHaveBeenCalled()
    expect(mockEditProvenance).not.toHaveBeenCalled()
  })

  it('shows provenance badges for agent-filled fields (AC-3)', async () => {
    mockSessionId = 'sess-3'
    mockGetSessionProvenance.mockResolvedValue({
      session: 3,
      groups: [
        {
          page: 3,
          label: 'Target Audience',
          fields: [
            {
              id: 30,
              field_name: 'audience_languages',
              extracted_value: ['en-IN'],
              status: 'PENDING',
              confidence: 0.8,
              wizard_page: 3,
            },
            {
              id: 31,
              field_name: 'customer_proof',
              extracted_value: [{ type: 'testimonial', text: 'Great' }],
              status: 'PENDING',
              confidence: 0.7,
              wizard_page: 3,
            },
          ],
        },
      ],
    })

    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 123,
            name: 'Test',
            audience_languages: ['en-IN'],
            customer_proof: [{ type: 'testimonial', text: 'Great' }],
          },
        ],
      }),
    })

    render(<TargetAudienceForm />)

    await waitFor(() => {
      expect(mockGetSessionProvenance).toHaveBeenCalledWith('sess-3')
    })

    await waitFor(() => {
      const badges = screen.getAllByText('AI')
      expect(badges.length).toBe(2)
    })
  })

  it('calls editProvenance on save for changed provenance fields (AC-3)', async () => {
    mockSessionId = 'sess-3'
    mockGetSessionProvenance.mockResolvedValue({
      session: 3,
      groups: [
        {
          page: 3,
          label: 'Target Audience',
          fields: [
            {
              id: 30,
              field_name: 'audience_languages',
              extracted_value: ['en-IN'],
              status: 'PENDING',
              confidence: 0.8,
              wizard_page: 3,
            },
          ],
        },
      ],
    })
    mockEditProvenance.mockResolvedValue({})

    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 123,
            name: 'Test',
            target_audience: 'SMBs',
            pain_points: 'Time',
            desired_outcomes: 'Speed',
            audience_languages: ['en-IN'],
          },
        ],
      }),
    })
    ;(apiClient.patch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 123 }),
    })

    render(<TargetAudienceForm />)

    await waitFor(() => {
      expect(screen.getByLabelText(/audience languages/i)).toHaveValue('en-IN')
    })

    fireEvent.change(screen.getByLabelText(/audience languages/i), {
      target: { value: 'en-IN, hi-IN' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalled()
    })

    await waitFor(() => {
      expect(mockEditProvenance).toHaveBeenCalledWith(30, ['en-IN', 'hi-IN'])
    })
  })
})
