// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest'

// Some envs lack localStorage at module-init; install an in-memory polyfill
// BEFORE importing modules that touch storage at top level.
if (typeof localStorage === 'undefined') {
  const store: Record<string, string> = {}
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = String(v) },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { for (const k of Object.keys(store)) delete store[k] },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() { return Object.keys(store).length },
  })
}

const { clearClientSession } = await import('./clearClientSession')
const { queryClient } = await import('./queryClient')
const { useChatStore } = await import('../stores/chatStore')
const { useModeStore } = await import('../stores/modeStore')
const { useSessionStore } = await import('../stores/sessionStore')

describe('clearClientSession (logout cache wipe — issue #112)', () => {
  beforeEach(() => {
    localStorage.clear()
    queryClient.clear()
    useChatStore.getState().setMessages([])
    useModeStore.setState({ modeId: null })
  })

  it('removes user-scoped localStorage keys', () => {
    localStorage.setItem('access_token', 'tok')
    localStorage.setItem('refresh_token', 'ref')
    localStorage.setItem('ib-chat', '{"x":1}')
    localStorage.setItem('info-broker.mode', '{"y":2}')
    localStorage.setItem('locked_pipelines', '["a"]')
    localStorage.setItem('ib-layout', '{"theme":"navy"}')

    clearClientSession()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(localStorage.getItem('ib-chat')).toBeNull()
    expect(localStorage.getItem('info-broker.mode')).toBeNull()
    expect(localStorage.getItem('locked_pipelines')).toBeNull()
    expect(localStorage.getItem('ib-layout')).toBe('{"theme":"navy"}')
  })

  it('empties the React Query cache so the next user cannot see prior data', () => {
    queryClient.setQueryData(['runs', 'user-a'], [{ id: 1, name: 'secret' }])
    expect(queryClient.getQueryData(['runs', 'user-a'])).toBeDefined()

    clearClientSession()

    expect(queryClient.getQueryData(['runs', 'user-a'])).toBeUndefined()
  })

  it('resets chatStore in-memory state (messages, sessionId, runs)', () => {
    useChatStore.getState().addMessage({ id: '1', role: 'user', content: 'hi' })
    useChatStore.getState().setSessionId('sess-a')
    useChatStore.getState().pushSessionRun('run-1')

    clearClientSession()

    const s = useChatStore.getState()
    expect(s.messages).toEqual([])
    expect(s.sessionId).toBeNull()
    expect(s.sessionRunIds).toEqual([])
  })

  it('resets modeStore in-memory state', () => {
    useModeStore.setState({ modeId: 'mode-a' })
    clearClientSession()
    expect(useModeStore.getState().modeId).toBeNull()
  })
})

describe('sessionStore.logout (issue #112)', () => {
  it('fully wipes session + caches when user logs out', () => {
    localStorage.setItem('access_token', 'tok')
    localStorage.setItem('refresh_token', 'ref')
    queryClient.setQueryData(['profile'], { name: 'alice' })
    useChatStore.getState().addMessage({ id: '1', role: 'user', content: 'private' })

    useSessionStore.getState().logout()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(queryClient.getQueryData(['profile'])).toBeUndefined()
    expect(useChatStore.getState().messages).toEqual([])
    expect(useSessionStore.getState().accessToken).toBeNull()
    expect(useSessionStore.getState().userId).toBeNull()
    expect(useSessionStore.getState().isAdmin).toBe(false)
  })
})
