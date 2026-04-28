export type ThemeMode = 'navy' | 'hacker'

export const THEMES: Record<ThemeMode, { label: string; icon: string }> = {
  navy:   { label: 'Deep Navy', icon: '☀' },
  hacker: { label: 'Hacker',    icon: '🌙' },
}

export function applyTheme(mode: ThemeMode): void {
  if (mode === 'hacker') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}
