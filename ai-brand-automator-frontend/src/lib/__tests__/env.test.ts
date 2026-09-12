import { env } from '@/lib/env'

describe('env configuration', () => {
  it('has default API URL in jsdom (browser context)', () => {
    // In jsdom, window.location.hostname is 'localhost', so getBaseApiUrl()
    // returns http://localhost:8000 via the browser path.
    expect(env.apiUrl).toBe('http://localhost:8000')
  })

  it('constructs full API URL correctly', () => {
    const url = env.getApiUrl('/companies/')
    expect(url).toBe('http://localhost:8000/api/v1/companies/')
  })

  it('handles paths without leading slash', () => {
    const url = env.getApiUrl('companies/')
    expect(url).toBe('http://localhost:8000/api/v1/companies/')
  })

  it('returns base URL when no path provided', () => {
    const url = env.getApiUrl()
    expect(url).toBe('http://localhost:8000/api/v1')
  })

  it('reports test environment correctly', () => {
    // Jest sets NODE_ENV=test
    expect(env.isTest).toBe(true)
  })

  it('validates configuration', () => {
    const result = env.validate()
    expect(result).toBe(true)
  })

  it('detects missing API URL in validation', () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    const testEnv = {
      ...env,
      apiUrl: '',
    }

    const result = testEnv.validate()
    expect(result).toBe(false)

    consoleSpy.mockRestore()
  })
})
