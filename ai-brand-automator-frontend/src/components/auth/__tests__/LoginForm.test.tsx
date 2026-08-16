import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginForm } from '@/components/auth/LoginForm'
import { apiClient } from '@/lib/api'

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    post: jest.fn(),
  },
}))

// Create mock router
const mockPush = jest.fn()
const mockReplace = jest.fn()

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: jest.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}))

describe('LoginForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    mockPush.mockClear()
    mockReplace.mockClear()
  })

  it('renders login form with email and password fields', () => {
    render(<LoginForm />)
    
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('displays validation errors for empty fields', async () => {
    render(<LoginForm />)
    
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    fireEvent.click(submitButton)
    
    // HTML5 validation should prevent submission
    const emailInput = screen.getByLabelText(/email address/i)
    expect(emailInput).toBeRequired()
  })

  it('submits form with valid credentials', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        access: 'mock-access-token',
        refresh: 'mock-refresh-token',
      }),
    }
    
    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)
    
    render(<LoginForm />)
    
    const emailInput = screen.getByLabelText(/email address/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/auth/login/', {
        email: 'test@example.com',
        password: 'password123',
      })
    }, { timeout: 3000 })
  })

  it('handles login failure with error message', async () => {
    const mockResponse = {
      ok: false,
      json: async () => ({
        detail: 'Invalid credentials',
      }),
    }
    
    ;(apiClient.post as jest.Mock).mockResolvedValue(mockResponse)
    
    // Mock alert
    const alertMock = jest.spyOn(window, 'alert').mockImplementation(() => {})
    
    render(<LoginForm />)
    
    const emailInput = screen.getByLabelText(/email address/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Invalid credentials')
    })
    
    alertMock.mockRestore()
  })

  it('handles network errors gracefully', async () => {
    ;(apiClient.post as jest.Mock).mockRejectedValue(new Error('Network error'))
    
    const alertMock = jest.spyOn(window, 'alert').mockImplementation(() => {})
    
    render(<LoginForm />)
    
    const emailInput = screen.getByLabelText(/email address/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(alertMock).toHaveBeenCalledWith('Login failed. Please try again.')
    })
    
    alertMock.mockRestore()
  })

  it('disables submit button while loading', async () => {
    const mockResponse = {
      ok: true,
      json: async () => ({
        access: 'token',
        refresh: 'token',
      }),
    }
    
    ;(apiClient.post as jest.Mock).mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve(mockResponse), 100))
    )
    
    render(<LoginForm />)
    
    const emailInput = screen.getByLabelText(/email address/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitButton)
    
    // Button should be disabled during submission
    expect(submitButton).toBeDisabled()
    
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalled()
    })
  })
})
