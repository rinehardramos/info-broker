import { useLayoutStore } from '../stores/layoutStore'
import { applyTheme, type ThemeMode } from '../lib/theme'
import { useCallback } from 'react'
import { updatePreferences } from '../api/v3'
import { useSessionStore } from '../stores/sessionStore'

export function useTheme() {
  const theme    = useLayoutStore(s => s.theme)
  const setTheme = useLayoutStore(s => s.setTheme)
  const token    = useSessionStore(s => s.accessToken)

  const toggle = useCallback(() => {
    const next: ThemeMode = theme === 'navy' ? 'hacker' : 'navy'
    setTheme(next)
    applyTheme(next)
    if (token) {
      updatePreferences({ theme: next }).catch(() => {/* ignore */})
    }
  }, [theme, setTheme, token])

  return { theme, toggle }
}
