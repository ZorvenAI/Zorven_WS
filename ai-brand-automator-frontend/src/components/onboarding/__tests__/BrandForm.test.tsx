import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrandForm } from '@/components/onboarding/BrandForm'
import { apiClient } from '@/lib/api'

jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
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
  getSessionProvenance: (...args: unknown[]) => mockGetSessionProvenance(...args),
  editProvenance: (...args: unknown[]) => mockEditProvenance(...args),
}))

describe('BrandForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
    window.localStorage.clear()
    window.alert = jest.fn()
    localStorage.setItem('company_id', '123')
    localStorage.setItem('access_token', 'test-token')
    mockSessionId = null
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    })
  })

  it('renders all brand strategy fields including business_goals', () => {
    render(<BrandForm />)

    expect(screen.getByLabelText(/brand voice/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/vision statement/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/mission statement/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/core values/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/positioning statement/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/business goals/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<BrandForm />)

    const brandVoiceInput = screen.getByLabelText(/brand voice/i)
    const visionInput = screen.getByLabelText(/vision statement/i)
    const missionInput = screen.getByLabelText(/mission statement/i)

    expect(brandVoiceInput).toBeRequired()
    expect(visionInput).not.toBeRequired()
    expect(missionInput).not.toBeRequired()
  })

  it('has brand voice dropdown with options', () => {
    render(<BrandForm />)

    const brandVoiceSelect = screen.getByLabelText(/brand voice/i)
    expect(brandVoiceSelect).toBeInTheDocument()

    const options = screen.getAllByRole('option')
    expect(options.length).toBeGreaterThan(3)
  })

  it('submits form with business_goals in PATCH payload', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<BrandForm />)

    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'professional' },
    })
    fireEvent.change(screen.getByLabelText(/vision statement/i), {
      target: { value: 'To transform the industry through innovation' },
    })
    fireEvent.change(screen.getByLabelText(/mission statement/i), {
      target: { value: 'We deliver exceptional solutions' },
    })
    fireEvent.change(screen.getByLabelText(/core values/i), {
      target: { value: 'Innovation, Excellence, Integrity' },
    })
    fireEvent.change(screen.getByLabelText(/business goals/i), {
      target: { value: 'Grow revenue 50% YoY' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        '/companies/123/',
        expect.objectContaining({
          brand_voice: 'professional',
          vision_statement: 'To transform the industry through innovation',
          mission_statement: 'We deliver exceptional solutions',
          values: 'Innovation, Excellence, Integrity',
          business_goals: 'Grow revenue 50% YoY',
        })
      )
    })
  })

  it('navigates to next step after successful submission', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)

    render(<BrandForm />)

    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'professional' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/onboarding/step-3')
    })
  })

  it('handles submission errors', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({
        detail: 'Failed to update company',
      }),
    }

    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)
    const alertMock = jest.fn()
    window.alert = alertMock

    render(<BrandForm />)

    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'professional' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Failed to update company')
    })

    expect(mockPush).not.toHaveBeenCalled()
  })

  it('disables submit button while loading', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 123 }),
    }

    ;(apiClient.patch as jest.Mock).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockResponse), 100))
    )

    render(<BrandForm />)

    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'professional' },
    })

    const submitButton = screen.getByRole('button', { name: /next step/i })
    fireEvent.click(submitButton)

    await waitFor(() => {
      expect(submitButton).toBeDisabled()
    })

    await waitFor(
      () => {
        expect(mockPush).toHaveBeenCalledWith('/onboarding/step-3')
      },
      { timeout: 200 }
    )
  })

  it('works without sessionId — no provenance fetch (AC-2)', async () => {
    mockSessionId = null
    ;(apiClient.patch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 123 }),
    })

    render(<BrandForm />)

    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'bold' },
    })
    fireEvent.change(screen.getByLabelText(/business goals/i), {
      target: { value: 'Scale internationally' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalled()
    })

    expect(mockGetSessionProvenance).not.toHaveBeenCalled()
    expect(mockEditProvenance).not.toHaveBeenCalled()
  })

  it('shows provenance badge for agent-filled business_goals (AC-3)', async () => {
    mockSessionId = 'sess-2'
    mockGetSessionProvenance.mockResolvedValue({
      session: 2,
      groups: [
        {
          page: 2,
          label: 'Brand Voice',
          fields: [
            {
              id: 20,
              field_name: 'business_goals',
              extracted_value: 'Expand to APAC',
              status: 'PENDING',
              confidence: 0.9,
              wizard_page: 2,
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
            brand_voice: 'friendly',
            business_goals: 'Expand to APAC',
          },
        ],
      }),
    })

    render(<BrandForm />)

    await waitFor(() => {
      expect(mockGetSessionProvenance).toHaveBeenCalledWith('sess-2')
    })

    await waitFor(() => {
      expect(screen.getByText('AI')).toBeInTheDocument()
    })
  })

  it('calls editProvenance on save when business_goals changes (AC-3)', async () => {
    mockSessionId = 'sess-2'
    mockGetSessionProvenance.mockResolvedValue({
      session: 2,
      groups: [
        {
          page: 2,
          label: 'Brand Voice',
          fields: [
            {
              id: 20,
              field_name: 'business_goals',
              extracted_value: 'Expand to APAC',
              status: 'PENDING',
              confidence: 0.9,
              wizard_page: 2,
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
            brand_voice: 'professional',
            business_goals: 'Expand to APAC',
          },
        ],
      }),
    })
    ;(apiClient.patch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 123 }),
    })

    render(<BrandForm />)

    await waitFor(() => {
      expect(screen.getByLabelText(/business goals/i)).toHaveValue(
        'Expand to APAC'
      )
    })

    fireEvent.change(screen.getByLabelText(/business goals/i), {
      target: { value: 'Expand to EMEA instead' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalled()
    })

    await waitFor(() => {
      expect(mockEditProvenance).toHaveBeenCalledWith(20, 'Expand to EMEA instead')
    })
  })
})
