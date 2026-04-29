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

  setTokens: (access: string, refresh: string) => void
  setUser: (id: string, username: string) => void
  setActiveJobId: (id: string | null) => void
  setAgentInput: (text: string) => void
  setCol1Content: (content: SessionState['col1Content']) => void
  logout: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: localStorage.getItem('access_token'),
  username: null,
  userId: null,
  activeJobId: null,
  agentInput: '',
  col1Content: null,

  setTokens: (access, refresh) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    set({ accessToken: access })
  },

  setUser: (id, username) => set({ userId: id, username }),

  setActiveJobId: (id) => set({ activeJobId: id }),

  setAgentInput: (text) => set({ agentInput: text }),

  setCol1Content: (content) => set({ col1Content: content }),

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ accessToken: null, username: null, userId: null, activeJobId: null, col1Content: null })
  },
}))
