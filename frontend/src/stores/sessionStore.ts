import { create } from 'zustand'

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

const storedToken = localStorage.getItem('access_token')
const initialClaims = claimsFromToken(storedToken)

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: localStorage.getItem('access_token'),
  username: null,
  userId:   initialClaims.userId,
  isAdmin:  initialClaims.isAdmin,
  role:     initialClaims.role,
  activeJobId: null,
  agentInput: '',
  col1Content: null,

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

  setActiveJobId: (id) => set({ activeJobId: id }),

  setAgentInput: (text) => set({ agentInput: text }),

  setCol1Content: (content) => set({ col1Content: content }),

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ accessToken: null, username: null, userId: null, activeJobId: null, col1Content: null, isAdmin: false, role: 'analyst' })
  },
}))
