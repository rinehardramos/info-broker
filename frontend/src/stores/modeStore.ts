import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ModeState = {
  modeId: string | null
  setModeId: (id: string | null) => void
}

export const useModeStore = create<ModeState>()(
  persist(
    (set) => ({
      modeId: null,
      setModeId: (id) => set({ modeId: id }),
    }),
    { name: 'info-broker.mode' },
  ),
)
