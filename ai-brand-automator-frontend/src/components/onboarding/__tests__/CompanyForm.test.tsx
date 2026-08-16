import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CompanyForm } from '@/components/onboarding/CompanyForm'
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
  }),
}))

describe('CompanyForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    // Default: no existing company
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    })
  })

  it('renders all form fields', () => {
    render(<CompanyForm />)

    expect(screen.getByLabelText(/company name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/industry/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/company description/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/target audience/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/core problem you solve/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<CompanyForm />)

    const nameInput = screen.getByLabelText(/company name/i)
    const industrySelect = screen.getByLabelText(/industry/i)
    const descriptionTextarea = screen.getByLabelText(/company description/i)

    expect(nameInput).toBeRequired()
    expect(industrySelect).toBeRequired()
    expect(descriptionTextarea).toBeRequired()
  })

  it('submits form with valid data', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        id: 1,
        name: 'Test Corp',
        industry: 'technology',
        description: 'A test company',
      }),
    }

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'Test Corp' },
    })
    fireEvent.change(screen.getByLabelText(/industry/i), {
      target: { value: 'technology' },
    })
    fireEvent.change(screen.getByLabelText(/company description/i), {
      target: { value: 'A test company' },
    })
    fireEvent.change(screen.getByLabelText(/target audience/i), {
      target: { value: 'Small businesses' },
    })
    fireEvent.change(screen.getByLabelText(/core problem you solve/i), {
      target: { value: 'Marketing automation' },
    })

    const submitButton = screen.getByRole('button', { name: /next step/i })
    fireEvent.click(submitButton)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/companies/',
        expect.objectContaining({
          name: 'Test Corp',
          industry: 'technology',
          description: 'A test company',
          target_audience: 'Small businesses',
          core_problem: 'Marketing automation',
        })
      )
    })

    await waitFor(() => {
      expect(localStorage.getItem('company_id')).toBe('1')
    })
  })

  it('converts camelCase to snake_case for backend', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 1 }),
    }

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'Test' },
    })
    fireEvent.change(screen.getByLabelText(/industry/i), {
      target: { value: 'technology' },
    })
    fireEvent.change(screen.getByLabelText(/company description/i), {
      target: { value: 'Test' },
    })
    fireEvent.change(screen.getByLabelText(/target audience/i), {
      target: { value: 'Test audience' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      const callArgs = (apiClient.post as jest.Mock).mock.calls[0][1]
      expect(callArgs).toHaveProperty('target_audience')
      expect(callArgs).toHaveProperty('core_problem')
      expect(callArgs).not.toHaveProperty('targetAudience')
      expect(callArgs).not.toHaveProperty('coreProblem')
    })
  })

  it('handles submission errors', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({
        detail: 'Invalid data',
      }),
    }

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    const alertMock = jest.spyOn(window, 'alert').mockImplementation(() => {})

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'Test' },
    })
    fireEvent.change(screen.getByLabelText(/industry/i), {
      target: { value: 'technology' },
    })
    fireEvent.change(screen.getByLabelText(/company description/i), {
      target: { value: 'Test' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Invalid data')
    })

    alertMock.mockRestore()
  })

  it('shows all industry options', () => {
    render(<CompanyForm />)

    const industrySelect = screen.getByLabelText(/industry/i)
    const options = Array.from(industrySelect.querySelectorAll('option'))

    const optionTexts = options.map(opt => opt.textContent)
    expect(optionTexts).toContain('Technology')
    expect(optionTexts).toContain('Healthcare')
    expect(optionTexts).toContain('Finance')
    expect(optionTexts).toContain('Retail')
    expect(optionTexts).toContain('Education')
    expect(optionTexts).toContain('Other')
  })
})
