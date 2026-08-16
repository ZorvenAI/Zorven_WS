import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TargetAudienceForm } from '@/components/onboarding/TargetAudienceForm'
import { apiClient } from '@/lib/api'

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    put: jest.fn(),
    patch: jest.fn(),
  },
}))

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}))

describe('TargetAudienceForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
    window.localStorage.clear()
    localStorage.setItem('company_id', '123')
    localStorage.setItem('access_token', 'test-token')
  })

  it('renders all target audience fields', () => {
    render(<TargetAudienceForm />)
    
    expect(screen.getByLabelText(/target audience/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/demographics/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/psychographics/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/pain points/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/desired outcomes/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<TargetAudienceForm />)
    
    const targetAudienceInput = screen.getByLabelText(/primary target audience/i)
    const painPointsInput = screen.getByLabelText(/key pain points/i)
    const desiredOutcomesInput = screen.getByLabelText(/desired outcomes/i)
    
    expect(targetAudienceInput).toBeRequired()
    expect(painPointsInput).toBeRequired()
    expect(desiredOutcomesInput).toBeRequired()
    
    // Demographics and psychographics are optional
    const demographicsInput = screen.getByLabelText(/^demographics$/i)
    const psychographicsInput = screen.getByLabelText(/^psychographics$/i)
    expect(demographicsInput).not.toBeRequired()
    expect(psychographicsInput).not.toBeRequired()
  })

  it('submits form with valid data', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        id: 123,
        target_audience: 'Updated demographics',
      }),
    }
    
    ;(apiClient.patch as jest.Mock).mockResolvedValue(mockResponse)
    
    render(<TargetAudienceForm />)
    
    fireEvent.change(screen.getByLabelText(/primary target audience/i), {
      target: { value: 'Small business owners' },
    })
    fireEvent.change(screen.getByLabelText(/^demographics$/i), {
      target: { value: 'Ages 30-50' },
    })
    fireEvent.change(screen.getByLabelText(/^psychographics$/i), {
      target: { value: 'Value efficiency' },
    })
    fireEvent.change(screen.getByLabelText(/key pain points/i), {
      target: { value: 'Limited time' },
    })
    fireEvent.change(screen.getByLabelText(/desired outcomes/i), {
      target: { value: 'Better productivity' },
    })
    
    fireEvent.click(screen.getByRole('button', { name: /next step/i }))
    
    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        '/companies/123/',
        expect.objectContaining({
          target_audience: 'Small business owners',
          demographics: 'Ages 30-50',
          psychographics: 'Value efficiency',
          pain_points: 'Limited time',
          desired_outcomes: 'Better productivity',
        })
      )
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
    
    ;(apiClient.patch as jest.Mock).mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockResponse), 100))
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
    
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/onboarding/step-4')
    }, { timeout: 3000 })
  })
})
