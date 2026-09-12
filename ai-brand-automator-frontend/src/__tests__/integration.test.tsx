import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginForm } from '@/components/auth/LoginForm'
import { RegisterForm } from '@/components/auth/RegisterForm'
import { CompanyForm } from '@/components/onboarding/CompanyForm'
import { ChatInterface } from '@/components/chat/ChatInterface'
import { apiClient } from '@/lib/api'

// Mock API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    post: jest.fn(),
    put: jest.fn(),
    get: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    postWithSignal: jest.fn(),
  },
}))

// Mock router
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}))

// ChatInterface depends on these hooks and child components
jest.mock('@/hooks/useBrandContext', () => ({
  useBrandContext: () => ({ activeBrand: null, refreshBrands: jest.fn() }),
}))

jest.mock('@/hooks/useTenantRole', () => ({
  useTenantRole: () => ({ role: 'owner', canEdit: true, canView: true }),
}))

jest.mock('@/hooks/useInputHistory', () => ({
  useInputHistory: () => ({
    history: [],
    pushMessage: jest.fn(),
    navigateUp: jest.fn().mockReturnValue(null),
    navigateDown: jest.fn().mockReturnValue(null),
    exitHistory: jest.fn(),
    setCurrentDraft: jest.fn(),
  }),
}))

interface MessageBubbleProps {
  message: { id: string; content: string };
}

jest.mock('@/components/chat/MessageBubble', () => ({
  MessageBubble: ({ message }: MessageBubbleProps) => (
    <div data-testid={`message-${message.id}`}>{message.content}</div>
  ),
}))

jest.mock('@/components/chat/ChatHistorySidebar', () => ({
  ChatHistorySidebar: () => <div data-testid="chat-history-sidebar">Chat History</div>,
}))

Element.prototype.scrollIntoView = jest.fn()

describe('Integration Tests: User Flows', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    mockPush.mockClear()
    window.alert = jest.fn()
    jest.spyOn(console, 'error').mockImplementation(() => {})
    jest.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 0
    })
    // Default: no existing company, no chat sessions
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    })
  })

  afterEach(() => {
    ;(window.requestAnimationFrame as jest.Mock).mockRestore()
    ;(console.error as jest.Mock).mockRestore()
  })

  describe('Registration → Login Flow', () => {
    it('allows user to register and then login', async () => {
      // Step 1: Register new user
      const registerResponse = {
        ok: true,
        json: async () => ({
          tokens: {
            access: 'register-token',
            refresh: 'register-refresh',
          },
        }),
      }

      ;(apiClient.post as jest.Mock).mockResolvedValueOnce(registerResponse)

      const { unmount } = render(<RegisterForm />)

      fireEvent.change(screen.getByLabelText(/email/i), {
        target: { value: 'newuser@example.com' },
      })
      fireEvent.change(screen.getByLabelText(/^password$/i), {
        target: { value: 'SecurePass123!' },
      })
      fireEvent.change(screen.getByLabelText(/confirm password/i), {
        target: { value: 'SecurePass123!' },
      })
      fireEvent.change(screen.getByLabelText(/first name/i), {
        target: { value: 'John' },
      })
      fireEvent.change(screen.getByLabelText(/last name/i), {
        target: { value: 'Doe' },
      })

      fireEvent.click(screen.getByRole('button', { name: /sign up/i }))

      await waitFor(() => {
        expect(localStorage.getItem('access_token')).toBe('register-token')
      }, { timeout: 3000 })

      unmount()
      localStorage.clear()

      // Step 2: Login with same credentials
      const loginResponse = {
        ok: true,
        json: async () => ({
          access: 'login-token',
          refresh: 'login-refresh',
        }),
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(loginResponse)

      render(<LoginForm />)

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: 'newuser@example.com' },
      })
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: 'SecurePass123!' },
      })

      fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith('/auth/login/', {
          email: 'newuser@example.com',
          password: 'SecurePass123!',
        })
      }, { timeout: 3000 })
    })
  })

  describe('Full Onboarding Flow', () => {
    it('completes company creation successfully', async () => {
      localStorage.setItem('access_token', 'test-token')

      // Mock GET /companies/ — no existing company
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      })

      // Mock POST /companies/
      const companyResponse = {
        ok: true,
        json: async () => ({
          id: '456',
          name: 'Integration Test Co',
          industry: 'technology',
        }),
      }

      ;(apiClient.post as jest.Mock).mockResolvedValue(companyResponse)

      render(<CompanyForm />)

      fireEvent.change(screen.getByLabelText(/company name/i), {
        target: { value: 'Integration Test Co' },
      })
      fireEvent.change(screen.getByLabelText(/industry/i), {
        target: { value: 'technology' },
      })
      fireEvent.change(screen.getByLabelText(/description/i), {
        target: { value: 'A test company for integration testing' },
      })
      fireEvent.change(screen.getByLabelText(/target audience/i), {
        target: { value: 'Tech professionals' },
      })
      fireEvent.change(screen.getByLabelText(/core problem/i), {
        target: { value: 'A test company for integration testing' },
      })

      fireEvent.click(screen.getByRole('button', { name: /next/i }))

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/onboarding/step-2')
        expect(localStorage.getItem('company_id')).toBe('456')
      }, { timeout: 3000 })
    })
  })

  describe('AI Chat Interaction Flow', () => {
    it('sends message and receives AI response', async () => {
      localStorage.setItem('access_token', 'test-token')

      const chatResponse = {
        ok: true,
        json: async () => ({
          session_id: 'session-123',
          response: 'Hello! How can I help you with your brand today?',
          thinking: '',
        }),
      }

      ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(chatResponse)

      render(<ChatInterface />)

      const input = screen.getByPlaceholderText(/ask me about your brand/i)
      const sendButton = screen.getByRole('button', { name: /send/i })

      fireEvent.change(input, {
        target: { value: 'Help me with brand strategy' },
      })
      fireEvent.click(sendButton)

      await waitFor(() => {
        expect(apiClient.postWithSignal).toHaveBeenCalledWith(
          '/ai/chat/',
          expect.objectContaining({ message: 'Help me with brand strategy' }),
          expect.any(AbortSignal)
        )
      }, { timeout: 3000 })

      await waitFor(() => {
        expect(screen.getByText(/how can i help you/i)).toBeInTheDocument()
      }, { timeout: 3000 })

      expect(input).toHaveValue('')
    })

    it('handles multiple message exchanges', async () => {
      localStorage.setItem('access_token', 'test-token')

      const responses = [
        {
          ok: true,
          json: async () => ({
            session_id: 'session-123',
            response: 'I can help you with that!',
            thinking: '',
          }),
        },
        {
          ok: true,
          json: async () => ({
            session_id: 'session-123',
            response: 'Here are some suggestions...',
            thinking: '',
          }),
        },
      ]

      ;(apiClient.postWithSignal as jest.Mock)
        .mockResolvedValueOnce(responses[0])
        .mockResolvedValueOnce(responses[1])

      render(<ChatInterface />)

      const input = screen.getByPlaceholderText(/ask me about your brand/i)
      const sendButton = screen.getByRole('button', { name: /send/i })

      // First message
      fireEvent.change(input, { target: { value: 'Hello' } })
      fireEvent.click(sendButton)

      await waitFor(() => {
        expect(screen.getByText(/i can help you/i)).toBeInTheDocument()
      }, { timeout: 3000 })

      // Second message
      fireEvent.change(input, { target: { value: 'Tell me more' } })
      fireEvent.click(sendButton)

      await waitFor(() => {
        expect(screen.getByText(/here are some suggestions/i)).toBeInTheDocument()
      }, { timeout: 3000 })

      expect(screen.getByText(/i can help you/i)).toBeInTheDocument()
      expect(screen.getByText(/here are some suggestions/i)).toBeInTheDocument()
    })
  })

  describe('Error Recovery Flow', () => {
    it('recovers from failed company creation and retries', async () => {
      localStorage.setItem('access_token', 'test-token')

      // Mock GET /companies/ — no existing company
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      })

      const alertMock = jest.fn()
      window.alert = alertMock

      // First attempt fails
      const errorResponse = {
        ok: false,
        json: async () => ({
          detail: 'Company name already exists',
        }),
      }

      // Second attempt succeeds
      const successResponse = {
        ok: true,
        json: async () => ({
          id: '789',
          name: 'Unique Company Name',
          industry: 'technology',
        }),
      }

      ;(apiClient.post as jest.Mock)
        .mockResolvedValueOnce(errorResponse)
        .mockResolvedValueOnce(successResponse)

      render(<CompanyForm />)

      // First attempt
      fireEvent.change(screen.getByLabelText(/company name/i), {
        target: { value: 'Duplicate Name' },
      })
      fireEvent.change(screen.getByLabelText(/industry/i), {
        target: { value: 'technology' },
      })
      fireEvent.change(screen.getByLabelText(/description/i), {
        target: { value: 'Test description' },
      })
      fireEvent.change(screen.getByLabelText(/target audience/i), {
        target: { value: 'Tech users' },
      })
      fireEvent.change(screen.getByLabelText(/core problem/i), {
        target: { value: 'Test problem' },
      })
      fireEvent.click(screen.getByRole('button', { name: /next/i }))

      await waitFor(() => {
        expect(alertMock).toHaveBeenCalledWith('Company name already exists')
      }, { timeout: 3000 })

      expect(mockPush).not.toHaveBeenCalled()

      // Second attempt with different name
      fireEvent.change(screen.getByLabelText(/company name/i), {
        target: { value: 'Unique Company Name' },
      })
      fireEvent.click(screen.getByRole('button', { name: /next/i }))

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/onboarding/step-2')
      }, { timeout: 3000 })
    })
  })
})
