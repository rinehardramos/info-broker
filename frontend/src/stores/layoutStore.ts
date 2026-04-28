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
  setTheme: (mode: ThemeMode) => void
  setSizes: (sizes: ColumnSizes) => void
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      theme: 'navy',
      sizes: { col1: 46, col2: 30, col3: 20 },
      setTheme: (theme) => set({ theme }),
      setSizes: (sizes) => set({ sizes }),
    }),
    { name: 'ib-layout' },
  ),
)
