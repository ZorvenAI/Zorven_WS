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
let mockSessionId: string | null = null
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
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

describe('CompanyForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    mockSessionId = null
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    })
  })

  it('renders all form fields including B-03 fields', () => {
    render(<CompanyForm />)

    expect(screen.getByLabelText(/company name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/industry/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/company description/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/legal name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/founder story/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/trademark status/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/decision maker/i)).toBeInTheDocument()
  })

  it('validates required fields', () => {
    render(<CompanyForm />)

    expect(screen.getByLabelText(/company name/i)).toBeRequired()
    expect(screen.getByLabelText(/industry/i)).toBeRequired()
    expect(screen.getByLabelText(/company description/i)).toBeRequired()
  })

  it('submits form with B-03 fields in PATCH payload', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 1, name: 'Test Corp' }),
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
    fireEvent.change(screen.getByLabelText(/legal name/i), {
      target: { value: 'Test Corp Pvt Ltd' },
    })
    fireEvent.change(screen.getByLabelText(/founder story/i), {
      target: { value: 'Started in a garage' },
    })
    fireEvent.change(screen.getByLabelText(/trademark status/i), {
      target: { value: 'registered' },
    })
    fireEvent.change(screen.getByLabelText(/decision maker/i), {
      target: { value: 'CEO John' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/companies/',
        expect.objectContaining({
          name: 'Test Corp',
          legal_name: 'Test Corp Pvt Ltd',
          founder_story: 'Started in a garage',
          trademark_status: 'registered',
          decision_maker: 'CEO John',
        })
      )
    })
  })

  it('works without sessionId — no provenance fetch (AC-2)', async () => {
    mockSessionId = null
    const mockResponse = {
      ok: true,
      json: async () => ({ id: 1 }),
    }
    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    render(<CompanyForm />)

    fireEvent.change(screen.getByLabelText(/company name/i), {
      target: { value: 'Manual Corp' },
    })
    fireEvent.change(screen.getByLabelText(/industry/i), {
      target: { value: 'retail' },
    })
    fireEvent.change(screen.getByLabelText(/company description/i), {
      target: { value: 'A manual entry' },
    })

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalled()
    })

    expect(mockGetSessionProvenance).not.toHaveBeenCalled()
    expect(mockEditProvenance).not.toHaveBeenCalled()
  })

  it('shows provenance badge for agent-filled fields (AC-3)', async () => {
    mockSessionId = 'sess-1'
    mockGetSessionProvenance.mockResolvedValue({
      session: 1,
      groups: [
        {
          page: 1,
          label: 'Company Info',
          fields: [
            {
              id: 10,
              session: 1,
              model_name: 'Company',
              field_name: 'legal_name',
              extracted_value: 'Acme Ltd',
              final_value: null,
              classification: 'SECONDARY',
              confidence: 0.85,
              source_recording: null,
              source_span: null,
              source_media: null,
              status: 'PENDING',
              reviewed_by: null,
              reviewed_at: null,
              wizard_page: 1,
              wizard_page_label: 'Company Info',
              created_at: '2026-08-01T00:00:00Z',
              updated_at: '2026-08-01T00:00:00Z',
            },
          ],
        },
      ],
    })

    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [{ id: 1, name: 'Test', legal_name: 'Acme Ltd' }],
      }),
    })

    render(<CompanyForm />)

    await waitFor(() => {
      expect(mockGetSessionProvenance).toHaveBeenCalledWith('sess-1')
    })

    await waitFor(() => {
      expect(screen.getByText('AI')).toBeInTheDocument()
    })
  })

  it('calls editProvenance on save for changed provenance fields (AC-3)', async () => {
    mockSessionId = 'sess-1'
    mockGetSessionProvenance.mockResolvedValue({
      session: 1,
      groups: [
        {
          page: 1,
          label: 'Company Info',
          fields: [
            {
              id: 10,
              field_name: 'legal_name',
              extracted_value: 'Acme Ltd',
              status: 'PENDING',
              confidence: 0.85,
              wizard_page: 1,
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
            id: 1,
            name: 'Test',
            description: 'Desc',
            industry: 'technology',
            legal_name: 'Acme Ltd',
          },
        ],
      }),
    })

    const patchResponse = {
      ok: true,
      json: async () => ({ id: 1 }),
    }
    ;(apiClient.patch as jest.Mock).mockResolvedValue(patchResponse)

    render(<CompanyForm />)

    await waitFor(() => {
      expect(screen.getByLabelText(/legal name/i)).toHaveValue('Acme Ltd')
    })

    fireEvent.change(screen.getByLabelText(/legal name/i), {
      target: { value: 'Acme Limited' },
    })

    fireEvent.click(screen.getByRole('button', { name: /update & continue/i }))

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalled()
    })

    await waitFor(() => {
      expect(mockEditProvenance).toHaveBeenCalledWith(10, 'Acme Limited')
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

    fireEvent.click(screen.getByRole('button', { name: /next step/i }))

    await waitFor(() => {
      const callArgs = (apiClient.post as jest.Mock).mock.calls[0][1]
      expect(callArgs).toHaveProperty('legal_name')
      expect(callArgs).toHaveProperty('founder_story')
      expect(callArgs).toHaveProperty('trademark_status')
      expect(callArgs).toHaveProperty('decision_maker')
      expect(callArgs).not.toHaveProperty('legalName')
      expect(callArgs).not.toHaveProperty('founderStory')
    })
  })

  it('handles submission errors', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({ detail: 'Invalid data' }),
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
  })
})
