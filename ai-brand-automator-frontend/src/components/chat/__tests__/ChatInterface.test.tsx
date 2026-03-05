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

describe('ChatInterface', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
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

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)
    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.change(input, { target: { value: 'What is my brand strategy?' } })
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/ai/chat/', {
        message: 'What is my brand strategy?',
      })
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

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

    render(<ChatInterface />)

    const input = screen.getByPlaceholderText(/Ask me about your brand strategy/i)

    fireEvent.change(input, { target: { value: 'Test message' } })
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalled()
    })
  })

  it('does not send empty messages', () => {
    render(<ChatInterface />)

    const sendButton = screen.getByRole('button', { name: /send/i })

    fireEvent.click(sendButton)

    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it('clears input after sending message', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        response: 'AI response',
        thinking: '',
      }),
    }

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

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

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

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

    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)

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
})
