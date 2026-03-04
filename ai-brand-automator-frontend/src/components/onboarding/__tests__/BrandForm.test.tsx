import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrandForm } from '@/components/onboarding/BrandForm'
import { apiClient } from '@/lib/api'

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    put: jest.fn(),
    post: jest.fn(),
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

describe('BrandForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
    window.localStorage.clear()
    window.alert = jest.fn()
    localStorage.setItem('company_id', '123')
    localStorage.setItem('access_token', 'test-token')
  })

  it('renders all brand strategy fields', () => {
    render(<BrandForm />)
    
    expect(screen.getByLabelText(/brand voice/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/vision statement/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/mission statement/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/core values/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/positioning statement/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<BrandForm />)
    
    const brandVoiceInput = screen.getByLabelText(/brand voice/i)
    const visionInput = screen.getByLabelText(/vision statement/i)
    const missionInput = screen.getByLabelText(/mission statement/i)
    
    expect(brandVoiceInput).toBeRequired()
    // Vision and mission are optional
    expect(visionInput).not.toBeRequired()
    expect(missionInput).not.toBeRequired()
  })

  it('has brand voice dropdown with options', () => {
    render(<BrandForm />)
    
    const brandVoiceSelect = screen.getByLabelText(/brand voice/i)
    expect(brandVoiceSelect).toBeInTheDocument()
    
    const options = screen.getAllByRole('option')
    expect(options.length).toBeGreaterThan(3) // At least professional, casual, friendly, authoritative
  })

  it('submits form with valid data', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        id: 123,
        vision_statement: 'Test vision',
        mission_statement: 'Test mission',
      }),
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
    
    fireEvent.click(screen.getByRole('button', { name: /next step/i }))
    
    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith(
        '/companies/123/',
        expect.objectContaining({
          brand_voice: 'professional',
          vision_statement: 'To transform the industry through innovation',
          mission_statement: 'We deliver exceptional solutions',
          values: 'Innovation, Excellence, Integrity',
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
    fireEvent.change(screen.getByLabelText(/vision statement/i), {
      target: { value: 'Vision' },
    })
    fireEvent.change(screen.getByLabelText(/mission statement/i), {
      target: { value: 'Mission' },
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
    fireEvent.change(screen.getByLabelText(/vision statement/i), {
      target: { value: 'Vision' },
    })
    fireEvent.change(screen.getByLabelText(/mission statement/i), {
      target: { value: 'Mission' },
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
    
    ;(apiClient.patch as jest.Mock).mockImplementation(() =>
      new Promise(resolve => setTimeout(() => resolve(mockResponse), 100))
    )
    
    render(<BrandForm />)
    
    fireEvent.change(screen.getByLabelText(/brand voice/i), {
      target: { value: 'professional' },
    })
    fireEvent.change(screen.getByLabelText(/vision statement/i), {
      target: { value: 'Vision' },
    })
    fireEvent.change(screen.getByLabelText(/mission statement/i), {
      target: { value: 'Mission' },
    })
    
    const submitButton = screen.getByRole('button', { name: /next step/i })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(submitButton).toBeDisabled()
    })
    
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/onboarding/step-3')
    }, { timeout: 200 })
  })
})
