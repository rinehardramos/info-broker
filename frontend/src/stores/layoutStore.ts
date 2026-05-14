import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ThemeMode } from '../lib/theme'

interface ColumnSizes {
  col1: number
  col2: number
  col3: number
}

interface LayoutState {
  theme: ThemeMode
  sizes: ColumnSizes
  runSplit: { top: number; bottom: number }
  setTheme: (mode: ThemeMode) => void
  setSizes: (sizes: ColumnSizes) => void
  setRunSplit: (split: { top: number; bottom: number }) => void
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      theme: 'navy',
      sizes: { col1: 46, col2: 30, col3: 20 },
      runSplit: { top: 60, bottom: 40 },
      setTheme: (theme) => set({ theme }),
      setSizes: (sizes) => set({ sizes }),
      setRunSplit: (runSplit) => set({ runSplit }),
    }),
    { name: 'ib-layout' },
  ),
)
