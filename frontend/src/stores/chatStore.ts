import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'agent'
  content: string
  status?: 'pending' | 'running' | 'done' | 'error'
  type?: 'message' | 'question' | 'plan' | 'confirm'
  payload?: Record<string, unknown>
}

interface ChatState {
  messages: Message[]
  sessionId: string | null
  genesisQuery: string | null
  sessionRunIds: string[]
  // Phase state for fast+thorough two-phase display
  fastResearchDone: boolean
  thoroughInProgress: boolean
  addMessage: (msg: Message) => void
  updateMessage: (id: string, patch: Partial<Message>) => void
  setMessages: (msgs: Message[]) => void
  setSessionId: (id: string) => void
  setGenesisQuery: (q: string) => void
  pushSessionRun: (runId: string) => void
  clearMessages: () => void
  setFastResearchDone: (done: boolean) => void
  setThoroughInProgress: (inProgress: boolean) => void
  appendBrainSuggestionAsMessage: (suggestion: { id: string; title: string; body?: string; payload?: Record<string, unknown> }) => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      sessionId: null,
      genesisQuery: null,
      sessionRunIds: [],
      fastResearchDone: false,
      thoroughInProgress: false,
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),
      setMessages: (messages) => set({ messages }),
      setSessionId: (id) => set({ sessionId: id }),
      setGenesisQuery: (q) => set({ genesisQuery: q }),
      pushSessionRun: (runId) => set((s) => ({ sessionRunIds: [...s.sessionRunIds, runId] })),
      clearMessages: () => set({ messages: [], sessionId: null, genesisQuery: null, sessionRunIds: [], fastResearchDone: false, thoroughInProgress: false }),
      setFastResearchDone: (done) => set({ fastResearchDone: done }),
      setThoroughInProgress: (inProgress) => set({ thoroughInProgress: inProgress }),
      appendBrainSuggestionAsMessage: (suggestion) =>
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: suggestion.id,
              role: 'assistant' as const,
              content: suggestion.body
                ? `**${suggestion.title}**\n\n${suggestion.body}`
                : suggestion.title,
              status: 'done' as const,
              type: 'plan' as const,
              payload: suggestion.payload,
            },
          ],
        })),
    }),
    {
      name: 'ib-chat',
      storage: createJSONStorage(() => localStorage),
    },
  ),
)
