/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-foreground)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-foreground)' },
        destructive: { DEFAULT: 'var(--destructive)', foreground: 'var(--destructive-foreground)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-foreground)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)' },
        card: { DEFAULT: 'var(--card)', foreground: 'var(--card-foreground)' },
        navy: {
          bg:      '#070e1a',
          panel:   '#0d1b2a',
          panel2:  '#132030',
          accent:  '#60a5fa',
          border:  '#1e3a5f',
          muted:   '#475569',
          text:    '#e2e8f0',
          subtext: '#94a3b8',
        },
        hacker: {
          bg:      '#050505',
          panel:   '#0a0a0a',
          panel2:  '#0d0d0d',
          accent:  '#22c55e',
          border:  '#1a2e1a',
          muted:   '#374151',
          text:    '#d1fae5',
          subtext: '#6b7280',
        },
        signal: {
          high:   '#4ade80',
          medium: '#f59e0b',
          low:    '#ef4444',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
