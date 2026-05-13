import { create } from 'zustand'

interface ResultDrawerState {
  isOpen: boolean
  runId: string | null
  open: (runId: string) => void
  close: () => void
}

export const useResultDrawerStore = create<ResultDrawerState>((set) => ({
  isOpen: false,
  runId: null,
  open: (runId) => set({ isOpen: true, runId }),
  close: () => set({ isOpen: false, runId: null }),
}))
