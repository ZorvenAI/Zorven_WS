// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'

// react-markdown is ESM-only and cannot be transformed by Jest's default
// pipeline. Mock it globally so any test importing a component that
// transitively depends on it (ChatInterface → MarkdownMessage) can run.
jest.mock('react-markdown', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require('react')
  return {
    __esModule: true,
    default: ({ children }) => React.createElement('div', { 'data-testid': 'markdown' }, children),
  }
})

jest.mock('remark-gfm', () => ({
  __esModule: true,
  default: () => {},
}))

jest.mock('rehype-highlight', () => ({
  __esModule: true,
  default: () => {},
}))

// Create a proper localStorage mock with actual storage
let store = {}

const createLocalStorageMock = () => ({
  getItem: jest.fn((key) => store[key] || null),
  setItem: jest.fn((key, value) => {
    store[key] = value.toString()
  }),
  removeItem: jest.fn((key) => {
    delete store[key]
  }),
  clear: jest.fn(() => {
    store = {}
  }),
})

global.localStorage = createLocalStorageMock()

// Mock fetch globally
global.fetch = jest.fn()

// Reset mocks before each test
beforeEach(() => {
  // Clear all mock call history
  jest.clearAllMocks()
  
  // Reset localStorage store and recreate mocks
  store = {}
  global.localStorage = createLocalStorageMock()
  
  // Clear fetch mock
  global.fetch.mockClear()
})
