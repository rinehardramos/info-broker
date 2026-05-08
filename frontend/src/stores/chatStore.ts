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
  addMessage: (msg: Message) => void
  updateMessage: (id: string, patch: Partial<Message>) => void
  setMessages: (msgs: Message[]) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      messages: [],
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),
      setMessages: (messages) => set({ messages }),
      clearMessages: () => set({ messages: [] }),
    }),
    {
      name: 'ib-chat',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
