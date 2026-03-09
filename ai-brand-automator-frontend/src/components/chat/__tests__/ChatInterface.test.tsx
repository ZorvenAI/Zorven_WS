import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ChatInterface } from '@/components/chat/ChatInterface'
import { apiClient } from '@/lib/api'

interface MessageBubbleProps {
  message: {
    id: string;
    content: string;
  };
}

jest.mock('@/lib/api', () => ({
  apiClient: {
    post: jest.fn(),
    postWithSignal: jest.fn(),
    get: jest.fn(),
    delete: jest.fn(),
  },
}))

// Mock child components
jest.mock('@/components/chat/MessageBubble', () => ({
  MessageBubble: ({ message }: MessageBubbleProps) => (
    <div data-testid={`message-${message.id}`}>
      {message.content}
    </div>
  ),
}))

jest.mock('@/components/chat/ChatHistorySidebar', () => ({
  ChatHistorySidebar: () => <div data-testid="chat-history-sidebar">Chat History</div>,
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

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}))

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = jest.fn()

describe('ChatInterface', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    // Mock requestAnimationFrame so hasMounted fires synchronously
    jest.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 0
    })
  })

  afterEach(() => {
    ;(window.requestAnimationFrame as jest.Mock).mockRestore()
  })

  it('renders with initial welcome message', () => {
    render(<ChatInterface />)

    expect(screen.getByRole('heading', { name: /AI brand assistant/i })).toBeInTheDocument()
    expect(screen.getByText(/Hello! I'm BranSol AI your brand assistant/i)).toBeInTheDocument()
  })

  it('renders input field and send button', () => {
    render(<ChatInterface />)

    expect(screen.getByPlaceholderText(/Ask me about your brand strategy/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument()
  })

  it('sends message when button is clicked', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        response: 'AI response message',
        thinking: '',
      }),
    }

    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)
    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.change(input, { target: { value: 'What is my brand strategy?' } })
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(apiClient.postWithSignal).toHaveBeenCalledWith(
        '/ai/chat/',
        { message: 'What is my brand strategy?' },
        expect.any(AbortSignal)
      )
    })

    await waitFor(() => {
      expect(screen.getByText('AI response message')).toBeInTheDocument()
    })
  })

  it('sends message when Enter key is pressed', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        response: 'AI response',
        thinking: '',
      }),
    }

    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)

    fireEvent.change(input, { target: { value: 'Test message' } })
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })

    await waitFor(() => {
      expect(apiClient.postWithSignal).toHaveBeenCalled()
    })
  })

  it('does not send empty messages', () => {
    render(<ChatInterface />)

    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.click(sendButton)

    expect(apiClient.postWithSignal).not.toHaveBeenCalled()
  })

  it('clears input after sending message', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        response: 'AI response',
        thinking: '',
      }),
    }

    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i) as HTMLTextAreaElement
    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.change(input, { target: { value: 'Test message' } })
    expect(input.value).toBe('Test message')

    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(input.value).toBe('')
    })
  })

  it('handles API errors gracefully', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({}),
    }

    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)
    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.change(input, { target: { value: 'Test' } })
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(screen.getByText(/Sorry, I encountered an error/i)).toBeInTheDocument()
    })
  })

  it('displays user and AI messages with correct styling', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        response: 'AI response',
        thinking: '',
      }),
    }

    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)

    fireEvent.change(input, { target: { value: 'User message' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByText('User message')).toBeInTheDocument()
      expect(screen.getByText('AI response')).toBeInTheDocument()
    })
  })

  it('renders ChatHistorySidebar', () => {
    render(<ChatInterface />)

    expect(screen.getByTestId('chat-history-sidebar')).toBeInTheDocument()
  })

  it('shows stop button while loading', async () => {
    // Create a mock that never resolves to keep the loading state
    ;(apiClient.postWithSignal as jest.Mock).mockReturnValue(new Promise(() => {}))

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)
    fireEvent.change(input, { target: { value: 'Test' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })
  })

  it('cancel button calls backend cancel endpoint', async () => {
    // First: send a message that establishes a session
    const firstResponse = {
      ok: true,
      json: async () => ({
        session_id: 'test-session-123',
        session_pk: 1,
        response: 'First reply',
        thinking: '',
      }),
    }
    ;(apiClient.postWithSignal as jest.Mock).mockResolvedValueOnce(firstResponse)

    render(<ChatInterface />)

    // Send first message to establish session
    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)
    fireEvent.change(input, { target: { value: 'First message' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByText('First reply')).toBeInTheDocument()
    })

    // Now: second message that never resolves (keeps loading)
    ;(apiClient.postWithSignal as jest.Mock).mockImplementation(
      (_url: string, _data: unknown, signal?: AbortSignal) => {
        return new Promise((_resolve, reject) => {
          if (signal) {
            signal.addEventListener('abort', () => {
              reject(new DOMException('Aborted', 'AbortError'))
            })
          }
        })
      }
    )
    ;(apiClient.post as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'cancel_requested' }),
    })

    fireEvent.change(input, { target: { value: 'Cancel this' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /stop/i }))

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/ai/chat/cancel/',
        expect.objectContaining({ session_id: 'test-session-123' })
      )
    })
  })
})
