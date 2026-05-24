import { create } from 'zustand'
import { clearClientSession } from '../lib/clearClientSession'

interface SessionState {
  accessToken: string | null
  username: string | null
  userId: string | null
  activeJobId: string | null
  agentInput: string
  col1Content:
    | { type: 'job'; jobId: string }
    | { type: 'pipeline_run'; runId: string }
    | null

  isAdmin: boolean
  role: string
  setTokens: (access: string, refresh: string) => void
  setUser: (id: string, username: string, isAdmin?: boolean) => void
  setIsAdmin: (isAdmin: boolean) => void
  setActiveJobId: (id: string | null) => void
  setAgentInput: (text: string) => void
  setCol1Content: (content: SessionState['col1Content']) => void
  logout: () => void
}

/** Decode JWT payload without verifying signature (verification happens server-side). */
function decodeJwt(token: string): Record<string, unknown> {
  try {
    const b64 = token.split('.')[1]
    const padded = b64 + '='.repeat((4 - b64.length % 4) % 4)
    return JSON.parse(atob(padded))
  } catch {
    return {}
  }
}

/** Extract isAdmin and role from the stored access token. */
function claimsFromToken(token: string | null): { isAdmin: boolean; userId: string | null; role: string } {
  if (!token) return { isAdmin: false, userId: null, role: 'analyst' }
  const p = decodeJwt(token)
  return {
    isAdmin: Boolean(p.is_admin),
    userId:  typeof p.sub === 'string' ? p.sub : null,
    role:    typeof p.role === 'string' ? p.role : 'analyst',
  }
}

function safeGetItem(key: string): string | null {
  try { return typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null }
  catch { return null }
}

const storedToken = safeGetItem('access_token')
const initialClaims = claimsFromToken(storedToken)

// Rehydrate the open Results tab across refreshes. clearClientSession() removes
// this key on logout so it doesn't leak between users on a shared browser.
const VIEW_KEY = 'ib-session-view'
type PersistedView = {
  activeJobId: string | null
  col1Content: SessionState['col1Content']
}
function loadPersistedView(): PersistedView {
  try {
    const raw = safeGetItem(VIEW_KEY)
    if (!raw) return { activeJobId: null, col1Content: null }
    const parsed = JSON.parse(raw) as Partial<PersistedView>
    return {
      activeJobId: parsed.activeJobId ?? null,
      col1Content: parsed.col1Content ?? null,
    }
  } catch {
    return { activeJobId: null, col1Content: null }
  }
}
function savePersistedView(view: PersistedView): void {
  try { localStorage.setItem(VIEW_KEY, JSON.stringify(view)) } catch { /* storage unavailable */ }
}
const initialView = loadPersistedView()

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: storedToken,
  username: null,
  userId:   initialClaims.userId,
  isAdmin:  initialClaims.isAdmin,
  role:     initialClaims.role,
  activeJobId: initialView.activeJobId,
  agentInput: '',
  col1Content: initialView.col1Content,

  setTokens: (access, refresh) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    const claims = claimsFromToken(access)
    set({ accessToken: access, isAdmin: claims.isAdmin, role: claims.role, userId: claims.userId })
  },

  setUser: (id, username, isAdmin) => set(s => ({
    userId: id,
    username,
    isAdmin: isAdmin !== undefined ? isAdmin : s.isAdmin,
  })),

  setIsAdmin: (isAdmin) => set({ isAdmin }),

  setActiveJobId: (id) => {
    set({ activeJobId: id })
    savePersistedView({ activeJobId: id, col1Content: useSessionStore.getState().col1Content })
  },

  setAgentInput: (text) => set({ agentInput: text }),

  setCol1Content: (content) => {
    set({ col1Content: content })
    savePersistedView({ activeJobId: useSessionStore.getState().activeJobId, col1Content: content })
  },

  logout: () => {
    clearClientSession()
    set({ accessToken: null, username: null, userId: null, activeJobId: null, col1Content: null, isAdmin: false, role: 'analyst' })
  },
}))

// Expose for E2E inspection / devtools.
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).useSessionStore = useSessionStore
}
