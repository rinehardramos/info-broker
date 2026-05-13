/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
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
