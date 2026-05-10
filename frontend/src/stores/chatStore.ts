import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'agent'
  content: string
  status?: 'pending' | 'running' | 'done' | 'error'
  type?: 'message' | 'question' | 'plan'
  payload?: Record<string, unknown>
}

interface ChatState {
  messages: Message[]
  sessionId: string | null
  genesisQuery: string | null
  addMessage: (msg: Message) => void
  updateMessage: (id: string, patch: Partial<Message>) => void
  setMessages: (msgs: Message[]) => void
  setSessionId: (id: string) => void
  setGenesisQuery: (q: string) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      sessionId: null,
      genesisQuery: null,
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),
      setMessages: (messages) => set({ messages }),
      setSessionId: (id) => set({ sessionId: id }),
      setGenesisQuery: (q) => set({ genesisQuery: q }),
      clearMessages: () => set({ messages: [], sessionId: null, genesisQuery: null }),
    }),
    {
      name: 'ib-chat',
      storage: createJSONStorage(() => localStorage),
    },
  ),
)
