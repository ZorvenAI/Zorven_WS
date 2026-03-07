import { renderHook, act } from '@testing-library/react'
import { useInputHistory } from '@/hooks/useInputHistory'

jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ history: [] }),
    }),
  },
}))

describe('useInputHistory', () => {
  beforeEach(() => {
    window.localStorage.clear()
    jest.clearAllMocks()
  })

  it('starts with empty history', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-1', sessionPk: null })
    )

    expect(result.current.history).toEqual([])
  })

  it('pushMessage adds to history', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-push', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('hello')
    })

    expect(result.current.history).toEqual(['hello'])
  })

  it('pushMessage caps at 50 entries', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-cap', sessionPk: null })
    )

    act(() => {
      for (let i = 0; i < 55; i++) {
        result.current.pushMessage(`msg-${i}`)
      }
    })

    expect(result.current.history.length).toBe(50)
    expect(result.current.history[49]).toBe('msg-54')
  })

  it('navigateUp returns most recent message', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-up', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('first')
      result.current.pushMessage('second')
      result.current.pushMessage('third')
    })

    let msg: string | null = null
    act(() => {
      msg = result.current.navigateUp()
    })

    expect(msg).toBe('third')
  })

  it('navigateUp cycles through history', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-cycle', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('first')
      result.current.pushMessage('second')
      result.current.pushMessage('third')
    })

    const msgs: (string | null)[] = []
    act(() => { msgs.push(result.current.navigateUp()) }) // third
    act(() => { msgs.push(result.current.navigateUp()) }) // second
    act(() => { msgs.push(result.current.navigateUp()) }) // first
    act(() => { msgs.push(result.current.navigateUp()) }) // null (at start)

    expect(msgs).toEqual(['third', 'second', 'first', null])
  })

  it('navigateDown returns draft past end', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-down', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('first')
      result.current.pushMessage('second')
      result.current.setCurrentDraft('my draft')
    })

    act(() => { result.current.navigateUp() }) // second
    act(() => { result.current.navigateUp() }) // first

    act(() => { result.current.navigateDown() }) // second

    let msg: string | null = null
    act(() => { msg = result.current.navigateDown() }) // past end → draft

    expect(msg).toBe('my draft')
  })

  it('exitHistory resets cursor', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-exit', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('msg')
    })

    act(() => {
      result.current.navigateUp()
    })

    act(() => {
      result.current.exitHistory()
    })

    // After exit, navigateDown should return null (cursor already -1)
    let msg: string | null = null
    act(() => {
      msg = result.current.navigateDown()
    })

    expect(msg).toBeNull()
  })

  it('persists to localStorage', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-persist', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('persisted message')
    })

    const stored = window.localStorage.getItem('chat_input_history_test-persist')
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored!)
    expect(parsed).toEqual(['persisted message'])
  })

  it('loads from localStorage on session change', () => {
    window.localStorage.setItem(
      'chat_input_history_test-load',
      JSON.stringify(['loaded-1', 'loaded-2'])
    )

    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-load', sessionPk: null })
    )

    expect(result.current.history).toEqual(['loaded-1', 'loaded-2'])
  })

  it('navigateDown returns null when not browsing', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-no-browse', sessionPk: null })
    )

    act(() => {
      result.current.pushMessage('msg')
    })

    let msg: string | null = null
    act(() => {
      msg = result.current.navigateDown()
    })

    expect(msg).toBeNull()
  })

  it('navigateUp returns null with empty history', () => {
    const { result } = renderHook(() =>
      useInputHistory({ sessionId: 'test-empty-up', sessionPk: null })
    )

    let msg: string | null = null
    act(() => {
      msg = result.current.navigateUp()
    })

    expect(msg).toBeNull()
  })
})
