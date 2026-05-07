# UI Platform — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full info-broker UI — login, 3-column research layout, agent chat, live stream, results panel, jobs, monitors, and settings with auto-rendered plugin config pages.

**Architecture:** Vite + React 18 SPA in `frontend/`. All data comes from the FastAPI backend at `/v3/*`. Real-time events arrive over a single WebSocket per session. Layout state (column widths/order, theme) is persisted via `PUT /v3/users/me/preferences`. The app is a thin shell — no business logic lives in the frontend.

**Tech Stack:** React 18, TypeScript, Tailwind CSS (class-based dark mode), Zustand (global state), TanStack Query (server state), Axios (HTTP + JWT interceptor), native WebSocket (custom hook), react-resizable-panels (column resizing), React Router v6, React Hook Form (plugin config forms), Vitest + @testing-library/react (tests)

---

## Scaffold State

The backend plan already created these files:
- `frontend/Dockerfile` — node:20-alpine dev server
- `frontend/package.json` — all deps pre-declared (react, zustand, @tanstack/react-query, axios, react-resizable-panels, @dnd-kit, react-hook-form, tailwindcss, vitest, @testing-library/react)
- `frontend/vite.config.ts` — Vite config with jsdom test environment
- `frontend/index.html` — HTML shell
- `frontend/src/main.tsx` — React root mount
- `frontend/src/App.tsx` — placeholder component
- `frontend/src/index.css` — minimal reset
- `frontend/src/test-setup.ts` — `@testing-library/jest-dom` import

**All new files go inside `frontend/`.**

---

## File Map

**Create:**
- `frontend/tailwind.config.js` — Tailwind with custom color tokens (navy/hacker modes)
- `frontend/postcss.config.js` — PostCSS for Tailwind
- `frontend/tsconfig.json` — TypeScript config
- `frontend/src/lib/theme.ts` — Color constants and CSS var helpers
- `frontend/src/api/client.ts` — Axios instance with JWT Bearer interceptor
- `frontend/src/api/auth.ts` — login(), refresh() calls
- `frontend/src/api/v3.ts` — all `/v3/*` API calls (agent, jobs, monitors, plugins, settings, preferences)
- `frontend/src/stores/sessionStore.ts` — Zustand: token, user, active job id
- `frontend/src/stores/layoutStore.ts` — Zustand: column widths, theme mode
- `frontend/src/hooks/useWebSocket.ts` — WebSocket singleton with reconnect + event dispatch
- `frontend/src/hooks/useTheme.ts` — read/write theme mode, apply CSS class
- `frontend/src/pages/Login.tsx` — login form
- `frontend/src/components/AuthGuard.tsx` — wraps protected routes
- `frontend/src/components/layout/IconRail.tsx` — 28px fixed right rail
- `frontend/src/components/layout/ThreeColumnLayout.tsx` — react-resizable-panels 3-col shell
- `frontend/src/components/agent/AgentChat.tsx` — Col 2: message list + pinned input
- `frontend/src/components/agent/MessageBubble.tsx` — single chat message
- `frontend/src/components/live/LiveStream.tsx` — Col 3: job/monitor event feed
- `frontend/src/components/live/JobItem.tsx` — single job event in live stream
- `frontend/src/components/results/ResultsPanel.tsx` — Col 1: tab bar + content
- `frontend/src/components/results/ProfileCard.tsx` — profile result card
- `frontend/src/components/results/NewsCard.tsx` — news result card
- `frontend/src/pages/Research.tsx` — main 3-col page (composes all three columns)
- `frontend/src/pages/Jobs.tsx` — jobs list page
- `frontend/src/pages/Monitors.tsx` — feed monitors CRUD page
- `frontend/src/pages/Settings.tsx` — core settings + plugin list
- `frontend/src/components/plugins/SchemaFormRenderer.tsx` — JSON Schema → React Hook Form fields
- `frontend/src/components/plugins/PluginConfigPage.tsx` — per-plugin config page

**Modify:**
- `frontend/src/App.tsx` — add React Router, QueryClientProvider, AuthGuard, all routes
- `frontend/src/index.css` — add Tailwind directives + CSS variables for both themes

**Tests:**
- `frontend/src/components/agent/AgentChat.test.tsx`
- `frontend/src/components/live/LiveStream.test.tsx`
- `frontend/src/components/results/ResultsPanel.test.tsx`
- `frontend/src/components/plugins/SchemaFormRenderer.test.tsx`
- `frontend/src/pages/Login.test.tsx`

---

## Task 1: Tailwind + TypeScript + Theme foundation

**Files:**
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/lib/theme.ts`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Create `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Deep Navy (light mode)
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
        // Hacker (dark mode)
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
        // Signal colours (both modes)
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
```

- [ ] **Step 2: Create `frontend/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts", "tailwind.config.js", "postcss.config.js"]
}
```

- [ ] **Step 5: Update `frontend/src/index.css` with Tailwind directives + CSS variables**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg:      #070e1a;
  --panel:   #0d1b2a;
  --panel2:  #132030;
  --accent:  #60a5fa;
  --border:  #1e3a5f;
  --muted:   #475569;
  --text:    #e2e8f0;
  --subtext: #94a3b8;
}

.dark {
  --bg:      #050505;
  --panel:   #0a0a0a;
  --panel2:  #0d0d0d;
  --accent:  #22c55e;
  --border:  #1a2e1a;
  --muted:   #374151;
  --text:    #d1fae5;
  --subtext: #6b7280;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden;   /* outer page never scrolls — columns do */
}

/* Each column scrolls independently */
.col-scroll {
  overflow-y: auto;
  height: 100%;
}

.col-scroll::-webkit-scrollbar { width: 4px; }
.col-scroll::-webkit-scrollbar-track { background: transparent; }
.col-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
```

- [ ] **Step 6: Create `frontend/src/lib/theme.ts`**

```typescript
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
```

- [ ] **Step 7: Verify Tailwind compiles inside Docker**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
docker compose restart frontend
sleep 8
curl -s http://localhost:5173 | grep -o 'vite/client'
```

Expected: `vite/client` (Vite dev server is serving)

- [ ] **Step 8: Commit**

```bash
git add frontend/tailwind.config.js frontend/postcss.config.js \
        frontend/tsconfig.json frontend/tsconfig.node.json \
        frontend/src/index.css frontend/src/lib/theme.ts
git commit -m "feat(frontend): Tailwind + TypeScript + theme foundation"
```

---

## Task 2: API client + Zustand stores

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/api/v3.ts`
- Create: `frontend/src/stores/sessionStore.ts`
- Create: `frontend/src/stores/layoutStore.ts`

- [ ] **Step 1: Create `frontend/src/api/client.ts`**

```typescript
import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api = axios.create({ baseURL: BASE })

// Attach stored access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401: try refresh, retry once, then redirect to /login
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE}/v3/auth/refresh`, { refresh_token: refresh })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          // refresh failed — fall through to redirect
        }
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)
```

- [ ] **Step 2: Create `frontend/src/api/auth.ts`**

```typescript
import { api } from './client'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/v3/auth/login', { username, password })
  return data
}
```

- [ ] **Step 3: Create `frontend/src/api/v3.ts`**

```typescript
import { api } from './client'

// --- Types ---

export interface UserOut {
  id: string
  username: string
  email: string | null
  is_active: boolean
  created_at: string
}

export interface PreferencesOut {
  theme: string
  column_layout: Record<string, unknown>
}

export interface JobOut {
  id: string
  status: string
  query: string
  created_at: string
  completed_at: string | null
  result_count: number
}

export interface MonitorOut {
  id: string
  name: string
  type: string
  target: string
  poll_interval_minutes: number
  last_polled_at: string | null
  last_item_count: number
  is_active: boolean
}

export interface PluginInfo {
  name: string
  description: string
  requires_api_key: boolean
  available: boolean
}

export interface CoreSettingsOut {
  settings: Record<string, string | null>
}

export interface AgentMessageOut {
  job_id: string
  status: string
}

// --- User ---

export const getMe = () => api.get<UserOut>('/v3/users/me').then(r => r.data)

export const getPreferences = () =>
  api.get<PreferencesOut>('/v3/users/me/preferences').then(r => r.data)

export const updatePreferences = (body: Partial<PreferencesOut>) =>
  api.put<PreferencesOut>('/v3/users/me/preferences', body).then(r => r.data)

// --- Agent ---

export const sendMessage = (message: string, context_job_id?: string) =>
  api.post<AgentMessageOut>('/v3/agent/message', { message, context_job_id }).then(r => r.data)

// --- Jobs ---

export const listJobs = () => api.get<JobOut[]>('/v3/jobs').then(r => r.data)

export const getJob = (id: string) => api.get<JobOut>(`/v3/jobs/${id}`).then(r => r.data)

export const cancelJob = (id: string) => api.delete(`/v3/jobs/${id}`)

// --- Monitors ---

export const listMonitors = () => api.get<MonitorOut[]>('/v3/monitors').then(r => r.data)

export const createMonitor = (body: { name: string; type: string; target: string; poll_interval_minutes: number }) =>
  api.post<MonitorOut>('/v3/monitors', body).then(r => r.data)

export const deleteMonitor = (id: string) => api.delete(`/v3/monitors/${id}`)

// --- Plugins ---

export const listPlugins = () => api.get<PluginInfo[]>('/v3/plugins').then(r => r.data)

export const getPluginSchema = (name: string) =>
  api.get<Record<string, unknown>>(`/v3/plugins/${name}/schema`).then(r => r.data)

export const getPluginConfig = (name: string) =>
  api.get<{ plugin_name: string; config: Record<string, unknown> }>(`/v3/plugins/${name}/config`).then(r => r.data)

export const savePluginConfig = (name: string, config: Record<string, unknown>) =>
  api.put(`/v3/plugins/${name}/config`, { config }).then(r => r.data)

// --- Core settings ---

export const getCoreSettings = () =>
  api.get<CoreSettingsOut>('/v3/settings/core').then(r => r.data)

export const updateCoreSettings = (items: { key: string; value: string; is_secret?: boolean }[]) =>
  api.put<CoreSettingsOut>('/v3/settings/core', items).then(r => r.data)
```

- [ ] **Step 4: Create `frontend/src/stores/sessionStore.ts`**

```typescript
import { create } from 'zustand'

interface SessionState {
  accessToken: string | null
  username: string | null
  userId: string | null
  activeJobId: string | null
  // Col 1 active result — set when user taps an item in Col 3
  col1Content: { type: 'job'; jobId: string } | null

  setTokens: (access: string, refresh: string) => void
  setUser: (id: string, username: string) => void
  setActiveJobId: (id: string | null) => void
  setCol1Content: (content: SessionState['col1Content']) => void
  logout: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: localStorage.getItem('access_token'),
  username: null,
  userId: null,
  activeJobId: null,
  col1Content: null,

  setTokens: (access, refresh) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    set({ accessToken: access })
  },

  setUser: (id, username) => set({ userId: id, username }),

  setActiveJobId: (id) => set({ activeJobId: id }),

  setCol1Content: (content) => set({ col1Content: content }),

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ accessToken: null, username: null, userId: null, activeJobId: null, col1Content: null })
  },
}))
```

- [ ] **Step 5: Create `frontend/src/stores/layoutStore.ts`**

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ThemeMode } from '../lib/theme'

interface ColumnSizes {
  col1: number  // percentage 0-100
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
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/ frontend/src/stores/
git commit -m "feat(frontend): API client + Zustand stores (session, layout)"
```

---

## Task 3: Login page + AuthGuard + App router

**Files:**
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/components/AuthGuard.tsx`
- Create: `frontend/src/pages/Login.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing login test**

Create `frontend/src/pages/Login.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock the auth api
vi.mock('../api/auth', () => ({
  login: vi.fn().mockResolvedValue({
    access_token: 'test-access',
    refresh_token: 'test-refresh',
    token_type: 'bearer',
  }),
}))

import Login from './Login'

function renderLogin() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Login', () => {
  it('renders username and password fields', () => {
    renderLogin()
    expect(screen.getByPlaceholderText('username')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('password')).toBeInTheDocument()
  })

  it('calls login on submit', async () => {
    const { login } = await import('../api/auth')
    renderLogin()
    fireEvent.change(screen.getByPlaceholderText('username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('password'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('admin', 'secret'))
  })
})
```

- [ ] **Step 2: Run test — expect FAIL (Login not defined)**

```bash
cd frontend && npm test -- --run src/pages/Login.test.tsx 2>&1 | tail -10
```

Expected: `Error: Failed to resolve import "./Login"`

- [ ] **Step 3: Create `frontend/src/pages/Login.tsx`**

```tsx
import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { useSessionStore } from '../stores/sessionStore'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const navigate                = useNavigate()
  const { setTokens }           = useSessionStore()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const tokens = await login(username, password)
      setTokens(tokens.access_token, tokens.refresh_token)
      navigate('/')
    } catch {
      setError('Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg)' }}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-72">
        <div className="text-lg font-bold mb-2" style={{ color: 'var(--accent)' }}>
          info-broker
        </div>
        <input
          placeholder="username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          className="px-3 py-2 rounded text-sm outline-none"
          style={{ background: 'var(--panel2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          autoComplete="username"
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          className="px-3 py-2 rounded text-sm outline-none"
          style={{ background: 'var(--panel2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          autoComplete="current-password"
        />
        {error && <span className="text-xs text-signal-low">{error}</span>}
        <button
          type="submit"
          disabled={loading}
          className="px-3 py-2 rounded text-sm font-semibold disabled:opacity-50"
          style={{ background: 'var(--accent)', color: 'var(--bg)' }}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/AuthGuard.tsx`**

```tsx
import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useSessionStore(s => s.accessToken)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 5: Rewrite `frontend/src/App.tsx`**

```tsx
import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AuthGuard from './components/AuthGuard'
import Login from './pages/Login'
import Research from './pages/Research'
import Jobs from './pages/Jobs'
import Monitors from './pages/Monitors'
import History from './pages/History'
import Settings from './pages/Settings'
import { useLayoutStore } from './stores/layoutStore'
import { applyTheme } from './lib/theme'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

export default function App() {
  const theme = useLayoutStore(s => s.theme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<AuthGuard><Research /></AuthGuard>} />
          <Route path="/jobs" element={<AuthGuard><Jobs /></AuthGuard>} />
          <Route path="/monitors" element={<AuthGuard><Monitors /></AuthGuard>} />
          <Route path="/history" element={<AuthGuard><History /></AuthGuard>} />
          <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
          <Route path="/settings/plugins/:name" element={<AuthGuard><Settings /></AuthGuard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
```

- [ ] **Step 6: Run login test — expect PASS**

```bash
cd frontend && npm test -- --run src/pages/Login.test.tsx 2>&1 | tail -10
```

Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/pages/Login.test.tsx \
        frontend/src/components/AuthGuard.tsx frontend/src/App.tsx
git commit -m "feat(frontend): Login page + AuthGuard + React Router"
```

---

## Task 4: WebSocket hook + theme hook

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/hooks/useTheme.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useWebSocket.ts`**

```typescript
import { useEffect, useRef, useCallback } from 'react'
import { useSessionStore } from '../stores/sessionStore'

export type WsEvent = {
  type: string
  job_id?: string
  plugin?: string
  status?: string
  result_count?: number
  message?: string
}

type Handler = (event: WsEvent) => void

// Singleton WebSocket shared across all hook consumers
let _ws: WebSocket | null = null
const _handlers = new Set<Handler>()
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null

function connect(token: string) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return

  const wsUrl = (import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/v3/stream') + `?token=${token}`
  _ws = new WebSocket(wsUrl)

  _ws.onmessage = (e) => {
    try {
      const event: WsEvent = JSON.parse(e.data)
      if (event.type !== 'ping') {
        _handlers.forEach(h => h(event))
      }
    } catch {
      // ignore malformed messages
    }
  }

  _ws.onclose = () => {
    _ws = null
    if (_reconnectTimer) clearTimeout(_reconnectTimer)
    _reconnectTimer = setTimeout(() => {
      const t = localStorage.getItem('access_token')
      if (t) connect(t)
    }, 3000)
  }

  _ws.onerror = () => {
    _ws?.close()
  }
}

export function useWebSocket(onEvent: Handler) {
  const token = useSessionStore(s => s.accessToken)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  const stableHandler = useCallback((e: WsEvent) => handlerRef.current(e), [])

  useEffect(() => {
    if (!token) return
    connect(token)
    _handlers.add(stableHandler)
    return () => { _handlers.delete(stableHandler) }
  }, [token, stableHandler])
}
```

- [ ] **Step 2: Create `frontend/src/hooks/useTheme.ts`**

```typescript
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
    // Persist to backend if logged in
    if (token) {
      updatePreferences({ theme: next }).catch(() => {/* ignore */})
    }
  }, [theme, setTheme, token])

  return { theme, toggle }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): WebSocket hook + theme toggle hook"
```

---

## Task 5: App shell — Icon rail + Three-column layout

**Files:**
- Create: `frontend/src/components/layout/IconRail.tsx`
- Create: `frontend/src/components/layout/ThreeColumnLayout.tsx`
- Create: `frontend/src/pages/Research.tsx`
- Create stub pages: `frontend/src/pages/Jobs.tsx`, `frontend/src/pages/Monitors.tsx`, `frontend/src/pages/History.tsx`, `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Create `frontend/src/components/layout/IconRail.tsx`**

```tsx
import { useNavigate, useLocation } from 'react-router-dom'
import { useTheme } from '../../hooks/useTheme'
import { useSessionStore } from '../../stores/sessionStore'
import { THEMES } from '../../lib/theme'

const NAV = [
  { icon: '⬡', path: '/',         label: 'Research' },
  { icon: '◉', path: '/jobs',     label: 'Jobs' },
  { icon: '◈', path: '/monitors', label: 'Monitors' },
  { icon: '▤', path: '/history',  label: 'History' },
  { icon: '⚙', path: '/settings', label: 'Settings' },
]

export default function IconRail() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { theme, toggle } = useTheme()
  const { logout, username } = useSessionStore()

  return (
    <div
      className="flex flex-col items-center py-3 gap-4 flex-shrink-0"
      style={{
        width: 28,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <span style={{ color: 'var(--accent)', fontSize: 11 }}>✦</span>

      <div className="flex-1 flex flex-col items-center gap-3 mt-2">
        {NAV.map(({ icon, path, label }) => {
          const active = location.pathname === path
          return (
            <button
              key={path}
              title={label}
              onClick={() => navigate(path)}
              className="flex items-center justify-center rounded transition-colors"
              style={{
                width: 20,
                height: 20,
                fontSize: 11,
                color: active ? 'var(--accent)' : 'var(--muted)',
                background: active ? 'var(--panel2)' : 'transparent',
                cursor: 'pointer',
                border: 'none',
              }}
            >
              {icon}
            </button>
          )
        })}
      </div>

      {/* Bottom: theme toggle + user avatar */}
      <div className="flex flex-col items-center gap-3">
        <button
          title={`Switch to ${theme === 'navy' ? 'Hacker' : 'Deep Navy'}`}
          onClick={toggle}
          style={{ fontSize: 10, color: 'var(--subtext)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          {THEMES[theme].icon}
        </button>
        <button
          title={`Logged in as ${username ?? '...'}`}
          onClick={logout}
          style={{
            width: 18, height: 18, borderRadius: '50%',
            background: 'var(--accent)', color: 'var(--bg)',
            fontSize: 9, fontWeight: 'bold', border: 'none', cursor: 'pointer',
          }}
        >
          {(username?.[0] ?? 'U').toUpperCase()}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/components/layout/ThreeColumnLayout.tsx`**

```tsx
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'
import { useLayoutStore } from '../../stores/layoutStore'
import { updatePreferences } from '../../api/v3'
import { useSessionStore } from '../../stores/sessionStore'

interface Props {
  col1: React.ReactNode
  col2: React.ReactNode
  col3: React.ReactNode
}

export default function ThreeColumnLayout({ col1, col2, col3 }: Props) {
  const { sizes, setSizes }   = useLayoutStore()
  const token                 = useSessionStore(s => s.accessToken)

  function handleResize(newSizes: number[]) {
    const next = { col1: newSizes[0], col2: newSizes[1], col3: newSizes[2] }
    setSizes(next)
    if (token) {
      updatePreferences({ column_layout: next }).catch(() => {/* ignore */})
    }
  }

  return (
    <PanelGroup
      direction="horizontal"
      onLayout={handleResize}
      style={{ height: '100%', flex: 1, overflow: 'hidden' }}
    >
      <Panel defaultSize={sizes.col1} minSize={20}>
        <div className="col-scroll h-full" style={{ background: 'var(--bg)' }}>
          {col1}
        </div>
      </Panel>

      <PanelResizeHandle
        style={{ width: 3, background: 'var(--border)', cursor: 'col-resize' }}
      />

      <Panel defaultSize={sizes.col2} minSize={15}>
        <div className="col-scroll h-full" style={{ background: 'var(--panel)' }}>
          {col2}
        </div>
      </Panel>

      <PanelResizeHandle
        style={{ width: 3, background: 'var(--border)', cursor: 'col-resize' }}
      />

      <Panel defaultSize={sizes.col3} minSize={10}>
        <div className="col-scroll h-full" style={{ background: 'var(--panel)' }}>
          {col3}
        </div>
      </Panel>
    </PanelGroup>
  )
}
```

- [ ] **Step 3: Create `frontend/src/pages/Research.tsx`** (wires the 3-col layout)

```tsx
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import ThreeColumnLayout from '../components/layout/ThreeColumnLayout'
import ResultsPanel from '../components/results/ResultsPanel'
import AgentChat from '../components/agent/AgentChat'
import LiveStream from '../components/live/LiveStream'
import { getMe } from '../api/v3'
import { useSessionStore } from '../stores/sessionStore'

export default function Research() {
  const { setUser } = useSessionStore()

  useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const user = await getMe()
      setUser(user.id, user.username)
      return user
    },
  })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <ThreeColumnLayout
        col1={<ResultsPanel />}
        col2={<AgentChat />}
        col3={<LiveStream />}
      />
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 4: Create stub pages (to satisfy router imports)**

`frontend/src/pages/Jobs.tsx`:
```tsx
import IconRail from '../components/layout/IconRail'
import { useQuery } from '@tanstack/react-query'
import { listJobs, type JobOut } from '../api/v3'

export default function Jobs() {
  const { data: jobs = [], isLoading } = useQuery({ queryKey: ['jobs'], queryFn: listJobs })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 col-scroll p-4">
        <h2 className="text-sm font-bold mb-4" style={{ color: 'var(--accent)' }}>Jobs</h2>
        {isLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {jobs.map((job: JobOut) => (
          <div key={job.id} className="mb-2 p-3 rounded text-xs" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--subtext)' }}>{job.status}</span>
            <span className="ml-2" style={{ color: 'var(--text)' }}>{job.query}</span>
          </div>
        ))}
      </div>
      <IconRail />
    </div>
  )
}
```

`frontend/src/pages/Monitors.tsx` (stub — full CRUD in Task 8):
```tsx
import IconRail from '../components/layout/IconRail'
export default function Monitors() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 p-4">
        <h2 className="text-sm font-bold" style={{ color: 'var(--accent)' }}>Feed Monitors</h2>
      </div>
      <IconRail />
    </div>
  )
}
```

`frontend/src/pages/History.tsx` (stub):
```tsx
import IconRail from '../components/layout/IconRail'
export default function History() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 p-4">
        <h2 className="text-sm font-bold" style={{ color: 'var(--accent)' }}>History</h2>
      </div>
      <IconRail />
    </div>
  )
}
```

`frontend/src/pages/Settings.tsx` (stub — full Settings in Task 9):
```tsx
import IconRail from '../components/layout/IconRail'
export default function Settings() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 p-4">
        <h2 className="text-sm font-bold" style={{ color: 'var(--accent)' }}>Settings</h2>
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 5: Verify in browser**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
docker compose restart frontend
sleep 10
curl -s http://localhost:5173 | grep -c 'vite'
```

Expected: `1` or more — Vite is serving. Open `http://localhost:5173/login` in browser and verify the login form renders with dark navy background.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/ frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat(frontend): app shell — icon rail + 3-column layout + stub pages"
```

---

## Task 6: Agent chat column (Col 2)

**Files:**
- Create: `frontend/src/components/agent/MessageBubble.tsx`
- Create: `frontend/src/components/agent/AgentChat.tsx`
- Create: `frontend/src/components/agent/AgentChat.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/agent/AgentChat.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api/v3', () => ({
  sendMessage: vi.fn().mockResolvedValue({ job_id: 'test-job-1', status: 'pending' }),
}))
vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))

import AgentChat from './AgentChat'

function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AgentChat', () => {
  it('renders message input', () => {
    wrap(<AgentChat />)
    expect(screen.getByPlaceholderText(/ask/i)).toBeInTheDocument()
  })

  it('sends message and shows user bubble', async () => {
    const { sendMessage } = await import('../../api/v3')
    wrap(<AgentChat />)
    const input = screen.getByPlaceholderText(/ask/i)
    fireEvent.change(input, { target: { value: 'find CTOs in Manila' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith('find CTOs in Manila', undefined)
    })
    expect(screen.getByText('find CTOs in Manila')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm test -- --run src/components/agent/AgentChat.test.tsx 2>&1 | tail -10
```

Expected: `Error: Failed to resolve import "./AgentChat"`

- [ ] **Step 3: Create `frontend/src/components/agent/MessageBubble.tsx`**

```tsx
interface Props {
  role: 'user' | 'agent'
  content: string
  status?: string   // 'pending' | 'running' | 'completed' | 'failed'
}

const statusColor: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  completed: 'var(--signal-high, #4ade80)',
  failed:    '#ef4444',
}

export default function MessageBubble({ role, content, status }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-2`}>
      <div
        className="max-w-[85%] px-3 py-2 rounded text-xs leading-relaxed"
        style={{
          background: isUser ? 'var(--accent)' : 'var(--panel2)',
          color:      isUser ? 'var(--bg)'     : 'var(--text)',
          border:     isUser ? 'none'           : '1px solid var(--border)',
        }}
      >
        {content}
        {status && (
          <span className="block mt-1 text-[10px]" style={{ color: statusColor[status] ?? 'var(--muted)' }}>
            ● {status}
          </span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/agent/AgentChat.tsx`**

```tsx
import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import MessageBubble from './MessageBubble'
import { sendMessage } from '../../api/v3'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useSessionStore } from '../../stores/sessionStore'

interface Message {
  id: string
  role: 'user' | 'agent'
  content: string
  status?: string
}

let _msgCounter = 0

export default function AgentChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [sending, setSending]   = useState(false)
  const { activeJobId, setActiveJobId } = useSessionStore()
  const bottomRef               = useRef<HTMLDivElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Handle WebSocket events
  useWebSocket((event: WsEvent) => {
    if (event.type === 'job.update' || event.type === 'job.completed' || event.type === 'job.failed') {
      setMessages(prev =>
        prev.map(m =>
          m.id === event.job_id
            ? { ...m, status: event.status }
            : m,
        ),
      )
      if (event.message && event.type === 'job.completed') {
        setMessages(prev => [
          ...prev,
          { id: `agent-${++_msgCounter}`, role: 'agent', content: event.message! },
        ])
      }
    }
    if (event.type === 'agent.message' && event.message) {
      setMessages(prev => [
        ...prev,
        { id: `agent-${++_msgCounter}`, role: 'agent', content: event.message! },
      ])
    }
  })

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)

    // Add user message immediately
    const userMsg: Message = { id: `user-${++_msgCounter}`, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])

    try {
      const result = await sendMessage(text, activeJobId ?? undefined)
      // Add agent placeholder with the job_id so WS events can update it
      setMessages(prev => [
        ...prev,
        { id: result.job_id, role: 'agent', content: `Research started…`, status: 'pending' },
      ])
      setActiveJobId(result.job_id)
    } catch {
      setMessages(prev => [
        ...prev,
        { id: `err-${++_msgCounter}`, role: 'agent', content: 'Failed to start research. Check your connection.' },
      ])
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2 text-[11px] font-semibold" style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}>
        Agent
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>
            Ask anything — I'll research it for you.
          </p>
        )}
        {messages.map(m => (
          <MessageBubble key={m.id} role={m.role} content={m.content} status={m.status} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input — pinned at bottom */}
      <div className="px-3 py-2" style={{ borderTop: '1px solid var(--border)' }}>
        <textarea
          placeholder="Ask info-broker… (Enter to send)"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={sending}
          rows={2}
          className="w-full text-xs px-2 py-2 rounded resize-none outline-none disabled:opacity-50"
          style={{
            background: 'var(--panel2)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Run test — expect PASS**

```bash
cd frontend && npm test -- --run src/components/agent/AgentChat.test.tsx 2>&1 | tail -10
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/agent/
git commit -m "feat(frontend): agent chat column with WebSocket job updates"
```

---

## Task 7: Live stream column (Col 3)

**Files:**
- Create: `frontend/src/components/live/JobItem.tsx`
- Create: `frontend/src/components/live/LiveStream.tsx`
- Create: `frontend/src/components/live/LiveStream.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/live/LiveStream.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('../../api/v3', () => ({
  listJobs: vi.fn().mockResolvedValue([
    { id: 'job-1', status: 'completed', query: 'find CTOs', created_at: '2026-04-28T00:00:00Z', completed_at: null, result_count: 5 },
  ]),
}))

import LiveStream from './LiveStream'

describe('LiveStream', () => {
  it('renders Live Stream header', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><LiveStream /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Live')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm test -- --run src/components/live/LiveStream.test.tsx 2>&1 | tail -5
```

- [ ] **Step 3: Create `frontend/src/components/live/JobItem.tsx`**

```tsx
import { useSessionStore } from '../../stores/sessionStore'
import type { JobOut } from '../../api/v3'

const statusStyle: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  completed: '#4ade80',
  failed:    '#ef4444',
  cancelled: 'var(--muted)',
}

interface Props {
  job: JobOut & { live?: boolean }
}

export default function JobItem({ job }: Props) {
  const setCol1Content = useSessionStore(s => s.setCol1Content)

  return (
    <div
      onClick={() => setCol1Content({ type: 'job', jobId: job.id })}
      className="px-3 py-2 mb-1 rounded cursor-pointer text-xs transition-colors"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-1 mb-1">
        <span style={{ color: statusStyle[job.status] ?? 'var(--muted)', fontSize: 8 }}>●</span>
        <span style={{ color: 'var(--subtext)', fontSize: 10 }}>{job.status}</span>
        {job.result_count > 0 && (
          <span className="ml-auto" style={{ color: 'var(--accent)', fontSize: 10 }}>
            {job.result_count} results
          </span>
        )}
      </div>
      <div className="truncate" style={{ color: 'var(--text)' }}>{job.query}</div>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/live/LiveStream.tsx`**

```tsx
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listJobs, type JobOut } from '../../api/v3'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import JobItem from './JobItem'

export default function LiveStream() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 30_000 })
  const [liveEvents, setLiveEvents] = useState<JobOut[]>([])

  useWebSocket((event: WsEvent) => {
    if (['job.update', 'job.completed', 'job.failed'].includes(event.type) && event.job_id) {
      setLiveEvents(prev => {
        const exists = prev.find(j => j.id === event.job_id)
        const updated: JobOut = exists
          ? { ...exists, status: event.status ?? exists.status, result_count: event.result_count ?? exists.result_count }
          : {
              id: event.job_id!,
              status: event.status ?? 'running',
              query: event.message ?? '…',
              created_at: new Date().toISOString(),
              completed_at: null,
              result_count: event.result_count ?? 0,
            }
        return exists ? prev.map(j => j.id === event.job_id ? updated : j) : [updated, ...prev]
      })
      if (event.type === 'job.completed') {
        qc.invalidateQueries({ queryKey: ['jobs'] })
      }
    }
  })

  // Merge live events with polled jobs; live events take priority
  const merged: JobOut[] = [
    ...liveEvents,
    ...jobs.filter(j => !liveEvents.find(l => l.id === j.id)),
  ].slice(0, 50)

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-[11px] font-semibold" style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}>
        Live
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {merged.length === 0 && (
          <p className="text-[10px] text-center mt-6" style={{ color: 'var(--muted)' }}>
            No active jobs
          </p>
        )}
        {merged.map(job => <JobItem key={job.id} job={job} />)}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Run test — expect PASS**

```bash
cd frontend && npm test -- --run src/components/live/LiveStream.test.tsx 2>&1 | tail -5
```

Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/live/
git commit -m "feat(frontend): live stream column with WebSocket job events"
```

---

## Task 8: Results panel (Col 1) + result cards

**Files:**
- Create: `frontend/src/components/results/ProfileCard.tsx`
- Create: `frontend/src/components/results/NewsCard.tsx`
- Create: `frontend/src/components/results/ResultsPanel.tsx`
- Create: `frontend/src/components/results/ResultsPanel.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/results/ResultsPanel.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import ResultsPanel from './ResultsPanel'

describe('ResultsPanel', () => {
  it('renders tab bar with Profiles, News, Social, Summary tabs', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><ResultsPanel /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Profiles')).toBeInTheDocument()
    expect(screen.getByText('News')).toBeInTheDocument()
    expect(screen.getByText('Social')).toBeInTheDocument()
    expect(screen.getByText('Summary')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm test -- --run src/components/results/ResultsPanel.test.tsx 2>&1 | tail -5
```

- [ ] **Step 3: Create `frontend/src/components/results/ProfileCard.tsx`**

```tsx
interface Profile {
  id: string
  first_name?: string
  last_name?: string
  headline?: string
  about?: string
}

export default function ProfileCard({ profile }: { profile: Profile }) {
  const name = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || '—'
  return (
    <div
      className="p-3 rounded mb-2 text-xs"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{name}</div>
      {profile.headline && (
        <div className="mb-1 truncate" style={{ color: 'var(--subtext)' }}>{profile.headline}</div>
      )}
      {profile.about && (
        <div className="line-clamp-3" style={{ color: 'var(--muted)' }}>{profile.about}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/results/NewsCard.tsx`**

```tsx
interface NewsItem {
  id: string
  title: string
  url?: string
  snippet?: string
  source_name?: string
  published_at?: string
}

export default function NewsCard({ item }: { item: NewsItem }) {
  return (
    <div
      className="p-3 rounded mb-2 text-xs"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      {item.url ? (
        <a href={item.url} target="_blank" rel="noopener noreferrer"
          className="font-semibold block mb-1 hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          {item.title}
        </a>
      ) : (
        <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{item.title}</div>
      )}
      {item.snippet && (
        <div className="line-clamp-2 mb-1" style={{ color: 'var(--subtext)' }}>{item.snippet}</div>
      )}
      <div className="flex gap-2" style={{ color: 'var(--muted)' }}>
        {item.source_name && <span>{item.source_name}</span>}
        {item.published_at && <span>{new Date(item.published_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create `frontend/src/components/results/ResultsPanel.tsx`**

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob } from '../../api/v3'
import NewsCard from './NewsCard'
import ProfileCard from './ProfileCard'

type Tab = 'Profiles' | 'News' | 'Social' | 'Summary'
const TABS: Tab[] = ['Profiles', 'News', 'Social', 'Summary']

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('News')
  const col1Content               = useSessionStore(s => s.col1Content)

  const { data: job } = useQuery({
    queryKey: ['job', col1Content?.jobId],
    queryFn: () => getJob(col1Content!.jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId,
  })

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center px-3 gap-1 pt-2 pb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-2 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: activeTab === tab ? 'var(--panel2)' : 'transparent',
              color:      activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              border:     activeTab === tab ? '1px solid var(--border)' : '1px solid transparent',
              cursor: 'pointer',
            }}
          >
            {tab}
          </button>
        ))}
        {col1Content && (
          <span className="ml-auto text-[10px] truncate max-w-[40%]" style={{ color: 'var(--subtext)' }}>
            {job?.query ?? '…'}
          </span>
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto p-3">
        {!col1Content && (
          <div className="text-center mt-16">
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              Send a message to the agent or tap a job in the live stream.
            </p>
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'News' && (
          <div>
            {/* News results from DDG search will appear here via job results API */}
            <p className="text-[10px] mb-3" style={{ color: 'var(--subtext)' }}>
              {job ? `Job ${job.status} — ${job.result_count} results` : 'Loading…'}
            </p>
            {job && job.result_count === 0 && (
              <NewsCard item={{
                id: 'placeholder',
                title: 'Research in progress',
                snippet: 'Results will appear here as the agent completes its research.',
              }} />
            )}
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'Summary' && (
          <div className="text-xs p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            {job ? (
              <>
                <div className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>{job.query}</div>
                <div style={{ color: 'var(--subtext)' }}>Status: {job.status}</div>
              </>
            ) : 'Loading…'}
          </div>
        )}

        {activeTab === 'Profiles' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Profile results appear here when LinkedIn plugin is active.</p>
        )}
        {activeTab === 'Social' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Social crawl results appear here.</p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run test — expect PASS**

```bash
cd frontend && npm test -- --run src/components/results/ResultsPanel.test.tsx 2>&1 | tail -5
```

Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/results/
git commit -m "feat(frontend): results panel with tab bar + profile/news cards"
```

---

## Task 9: Monitors page (full CRUD)

**Files:**
- Modify: `frontend/src/pages/Monitors.tsx`

- [ ] **Step 1: Rewrite `frontend/src/pages/Monitors.tsx`**

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listMonitors, createMonitor, deleteMonitor, type MonitorOut } from '../api/v3'
import IconRail from '../components/layout/IconRail'

export default function Monitors() {
  const qc = useQueryClient()
  const { data: monitors = [], isLoading } = useQuery({ queryKey: ['monitors'], queryFn: listMonitors })

  const [name, setName]   = useState('')
  const [type, setType]   = useState('rss')
  const [target, setTarget] = useState('')
  const [interval, setInterval] = useState(60)

  const create = useMutation({
    mutationFn: () => createMonitor({ name, type, target, poll_interval_minutes: interval }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monitors'] })
      setName(''); setTarget('')
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteMonitor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['monitors'] }),
  })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 col-scroll p-4">
        <h2 className="text-sm font-bold mb-4" style={{ color: 'var(--accent)' }}>Feed Monitors</h2>

        {/* Add monitor form */}
        <div className="mb-4 p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
          <div className="text-[11px] font-semibold mb-2" style={{ color: 'var(--subtext)' }}>Add Monitor</div>
          <div className="flex flex-col gap-2">
            <input placeholder="Name" value={name} onChange={e => setName(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <select value={type} onChange={e => setType(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}>
              <option value="rss">RSS</option>
              <option value="twitter">Twitter / X</option>
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook</option>
            </select>
            <input placeholder="URL or @handle" value={target} onChange={e => setTarget(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <input type="number" placeholder="Poll interval (min)" value={interval}
              onChange={e => setInterval(Number(e.target.value))}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <button
              onClick={() => create.mutate()}
              disabled={!name || !target || create.isPending}
              className="px-3 py-1 rounded text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--accent)', color: 'var(--bg)', cursor: 'pointer', border: 'none' }}
            >
              {create.isPending ? 'Adding…' : 'Add Monitor'}
            </button>
          </div>
        </div>

        {isLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {monitors.map((m: MonitorOut) => (
          <div key={m.id} className="mb-2 p-3 rounded flex items-center justify-between text-xs"
            style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text)' }}>{m.name}</span>
              <span className="ml-2" style={{ color: 'var(--subtext)' }}>{m.type} · {m.target}</span>
              {m.last_polled_at && (
                <span className="ml-2" style={{ color: 'var(--muted)' }}>
                  polled {new Date(m.last_polled_at).toLocaleString()}
                </span>
              )}
            </div>
            <button
              onClick={() => remove.mutate(m.id)}
              style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11 }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Monitors.tsx
git commit -m "feat(frontend): monitors page with CRUD"
```

---

## Task 10: Settings page — Core settings + Plugin config auto-renderer

**Files:**
- Create: `frontend/src/components/plugins/SchemaFormRenderer.tsx`
- Create: `frontend/src/components/plugins/SchemaFormRenderer.test.tsx`
- Create: `frontend/src/components/plugins/PluginConfigPage.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/plugins/SchemaFormRenderer.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import SchemaFormRenderer from './SchemaFormRenderer'

function Wrapper({ schema }: { schema: Record<string, unknown> }) {
  const methods = useForm()
  return (
    <FormProvider {...methods}>
      <SchemaFormRenderer schema={schema} />
    </FormProvider>
  )
}

describe('SchemaFormRenderer', () => {
  it('renders string field from schema', () => {
    render(<Wrapper schema={{
      type: 'object',
      properties: {
        actor_id: { type: 'string', title: 'Actor ID', default: 'apify/linkedin' },
      },
    }} />)
    expect(screen.getByLabelText('Actor ID')).toBeInTheDocument()
  })

  it('renders integer field with min/max', () => {
    render(<Wrapper schema={{
      type: 'object',
      properties: {
        max_results: { type: 'integer', title: 'Max Results', default: 25, minimum: 1, maximum: 200 },
      },
    }} />)
    const input = screen.getByLabelText('Max Results')
    expect(input).toHaveAttribute('type', 'number')
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('max', '200')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm test -- --run src/components/plugins/SchemaFormRenderer.test.tsx 2>&1 | tail -5
```

- [ ] **Step 3: Create `frontend/src/components/plugins/SchemaFormRenderer.tsx`**

```tsx
import { useFormContext } from 'react-hook-form'

interface JSONSchemaProperty {
  type: string
  title?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: string[]
  description?: string
}

interface SchemaObject {
  type: string
  properties?: Record<string, JSONSchemaProperty>
}

interface Props {
  schema: Record<string, unknown>
}

const inputStyle = {
  background: 'var(--panel)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
}

export default function SchemaFormRenderer({ schema }: Props) {
  const { register } = useFormContext()
  const s = schema as SchemaObject

  if (!s.properties) {
    return <p className="text-xs" style={{ color: 'var(--muted)' }}>No configuration options.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {Object.entries(s.properties).map(([key, prop]) => {
        const id = `field-${key}`
        return (
          <div key={key} className="flex flex-col gap-1">
            <label htmlFor={id} className="text-[11px]" style={{ color: 'var(--subtext)' }}>
              {prop.title ?? key}
            </label>

            {prop.enum ? (
              <select
                id={id}
                {...register(key)}
                defaultValue={String(prop.default ?? '')}
                className="px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              >
                {prop.enum.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : prop.type === 'boolean' ? (
              <input
                id={id}
                type="checkbox"
                {...register(key)}
                defaultChecked={Boolean(prop.default)}
                className="w-4 h-4"
              />
            ) : (
              <input
                id={id}
                type={prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'}
                {...register(key)}
                defaultValue={String(prop.default ?? '')}
                min={prop.minimum}
                max={prop.maximum}
                className="px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              />
            )}

            {prop.description && (
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>{prop.description}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm test -- --run src/components/plugins/SchemaFormRenderer.test.tsx 2>&1 | tail -5
```

Expected: `2 passed`

- [ ] **Step 5: Create `frontend/src/components/plugins/PluginConfigPage.tsx`**

```tsx
import { useEffect } from 'react'
import { useForm, FormProvider } from 'react-hook-form'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPluginSchema, getPluginConfig, savePluginConfig } from '../../api/v3'
import SchemaFormRenderer from './SchemaFormRenderer'

interface Props { pluginName: string }

export default function PluginConfigPage({ pluginName }: Props) {
  const qc = useQueryClient()
  const methods = useForm()

  const { data: schema } = useQuery({
    queryKey: ['plugin-schema', pluginName],
    queryFn: () => getPluginSchema(pluginName),
  })

  const { data: saved } = useQuery({
    queryKey: ['plugin-config', pluginName],
    queryFn: () => getPluginConfig(pluginName),
  })

  // Pre-fill form with saved config
  useEffect(() => {
    if (saved?.config) methods.reset(saved.config)
  }, [saved, methods])

  const save = useMutation({
    mutationFn: (data: Record<string, unknown>) => savePluginConfig(pluginName, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plugin-config', pluginName] }),
  })

  return (
    <div className="p-4">
      <div className="text-sm font-semibold mb-3 capitalize" style={{ color: 'var(--accent)' }}>
        {pluginName} Plugin
      </div>

      {schema ? (
        <FormProvider {...methods}>
          <form onSubmit={methods.handleSubmit(data => save.mutate(data as Record<string, unknown>))}>
            <SchemaFormRenderer schema={schema} />
            <button
              type="submit"
              disabled={save.isPending}
              className="mt-4 px-4 py-2 rounded text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
            >
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
            {save.isSuccess && (
              <span className="ml-3 text-xs" style={{ color: '#4ade80' }}>Saved</span>
            )}
          </form>
        </FormProvider>
      ) : (
        <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading schema…</p>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Rewrite `frontend/src/pages/Settings.tsx`**

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getCoreSettings, updateCoreSettings, listPlugins, type PluginInfo } from '../api/v3'
import { useForm } from 'react-hook-form'
import IconRail from '../components/layout/IconRail'
import PluginConfigPage from '../components/plugins/PluginConfigPage'

type Section = 'core' | string  // 'core' or plugin name

const CORE_FIELDS = [
  { key: 'db.postgres_url',        label: 'Postgres URL',         secret: false },
  { key: 'db.qdrant_host',         label: 'Qdrant Host',          secret: false },
  { key: 'rag.embedding_model',    label: 'Embedding Model',      secret: false },
  { key: 'llm.active_provider',    label: 'Active LLM Provider',  secret: false },
  { key: 'llm.openai.api_key',     label: 'OpenAI API Key',       secret: true },
  { key: 'llm.anthropic.api_key',  label: 'Anthropic API Key',    secret: true },
  { key: 'llm.gemini.api_key',     label: 'Gemini API Key',       secret: true },
  { key: 'llm.lmstudio.base_url',  label: 'LM Studio Base URL',   secret: false },
  { key: 'jwt.secret',             label: 'JWT Secret',           secret: true },
  { key: 'jwt.expiry_hours',       label: 'JWT Expiry (hours)',    secret: false },
]

function CoreSettingsForm() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['core-settings'], queryFn: getCoreSettings })
  const { register, handleSubmit } = useForm()

  const save = useMutation({
    mutationFn: (values: Record<string, string>) =>
      updateCoreSettings(
        CORE_FIELDS
          .filter(f => values[f.key] !== undefined && values[f.key] !== '')
          .map(f => ({ key: f.key, value: values[f.key], is_secret: f.secret }))
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['core-settings'] }),
  })

  return (
    <form onSubmit={handleSubmit(v => save.mutate(v as Record<string, string>))} className="flex flex-col gap-3">
      {CORE_FIELDS.map(f => (
        <div key={f.key} className="flex flex-col gap-1">
          <label className="text-[11px]" style={{ color: 'var(--subtext)' }}>{f.label}</label>
          <input
            type={f.secret ? 'password' : 'text'}
            placeholder={data?.settings[f.key] === null ? '••••••••' : (data?.settings[f.key] ?? '')}
            {...register(f.key)}
            className="px-2 py-1 rounded text-xs outline-none"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={save.isPending}
        className="mt-2 px-4 py-2 rounded text-xs font-semibold w-fit disabled:opacity-50"
        style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
      >
        {save.isPending ? 'Saving…' : 'Save Core Settings'}
      </button>
      {save.isSuccess && <span className="text-xs" style={{ color: '#4ade80' }}>Saved</span>}
    </form>
  )
}

export default function Settings() {
  const params           = useParams<{ name?: string }>()
  const [section, setSection] = useState<Section>(params.name ?? 'core')
  const { data: plugins = [] } = useQuery({ queryKey: ['plugins'], queryFn: listPlugins })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex h-full flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-40 flex-shrink-0 col-scroll py-3 px-2" style={{ background: 'var(--panel)', borderRight: '1px solid var(--border)' }}>
          <div className="text-[10px] font-semibold mb-2 px-1" style={{ color: 'var(--muted)' }}>SYSTEM</div>
          <button
            onClick={() => setSection('core')}
            className="w-full text-left px-2 py-1 rounded text-xs mb-1"
            style={{
              background: section === 'core' ? 'var(--panel2)' : 'transparent',
              color: section === 'core' ? 'var(--accent)' : 'var(--text)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Core Settings
          </button>

          <div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>PLUGINS</div>
          {plugins.map((p: PluginInfo) => (
            <button
              key={p.name}
              onClick={() => setSection(p.name)}
              className="w-full text-left px-2 py-1 rounded text-xs mb-1"
              style={{
                background: section === p.name ? 'var(--panel2)' : 'transparent',
                color: section === p.name ? 'var(--accent)' : 'var(--text)',
                border: 'none', cursor: 'pointer',
              }}
            >
              {p.name}
              {!p.available && <span className="ml-1 text-[9px]" style={{ color: '#ef4444' }}>✕</span>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 col-scroll p-4">
          <h2 className="text-sm font-bold mb-4 capitalize" style={{ color: 'var(--accent)' }}>
            {section === 'core' ? 'Core Settings' : `${section} Plugin`}
          </h2>
          {section === 'core' ? (
            <CoreSettingsForm />
          ) : (
            <PluginConfigPage pluginName={section} />
          )}
        </div>
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/plugins/ frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): settings page + auto-rendered plugin config forms"
```

---

## Task 11: Final smoke test

- [ ] **Step 1: Run all frontend tests**

```bash
cd frontend && npm test -- --run 2>&1 | tail -15
```

Expected: All tests pass.

- [ ] **Step 2: Rebuild and restart docker compose**

```bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
docker compose up --build -d
```

- [ ] **Step 3: Verify all services healthy**

```bash
sleep 8
curl -s http://localhost:8000/healthz
# Expected: {"status":"ok"}

curl -s http://localhost:5173 | grep -c 'vite'
# Expected: 1 or more

curl -s http://localhost:8000/openapi.json | python3 -c "import json,sys; paths=json.load(sys.stdin)['paths']; v3=[p for p in paths if p.startswith('/v3')]; print(f'{len(v3)} v3 routes')"
# Expected: 13 v3 routes
```

- [ ] **Step 4: Manual smoke in browser**

Open `http://localhost:5173`:
- Should redirect to `/login` (token not present)
- Login form shows in dark navy
- After login → redirected to `/` (Research page, 3-column layout)
- Icon rail on right with `⬡ ◉ ◈ ▤ ⚙` icons
- Col 2 shows "Ask info-broker…" input
- Col 3 shows "No active jobs"
- Type a message → should return a job_id (requires Postgres)
- `☀` / `🌙` toggle switches to hacker mode (green accent, black bg)
- Navigate to `/settings` → Core Settings form, plugin list on left sidebar

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat(frontend): complete UI platform — research layout, agent, live stream, settings"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| 3-column layout (resizable) | Task 5 — ThreeColumnLayout + react-resizable-panels |
| Icon rail 28px, right-handed | Task 5 — IconRail |
| Deep Navy + Hacker modes | Task 1 (tokens), Task 4 (useTheme) |
| Theme persisted per user | Task 4 — updatePreferences on toggle |
| Column widths persisted | Task 5 — layoutStore + updatePreferences on resize |
| Col 2 agent chat + pinned input | Task 6 — AgentChat |
| Col 3 live stream, tap → Col 1 | Task 7 — LiveStream + JobItem + setCol1Content |
| Col 1 tab bar (Profiles/News/Social/Summary) | Task 8 — ResultsPanel |
| WebSocket live events | Task 4 — useWebSocket singleton |
| JWT auth + AuthGuard | Task 3 — Login + AuthGuard |
| Token refresh interceptor | Task 2 — client.ts |
| Plugin config auto-rendered from JSON Schema | Task 10 — SchemaFormRenderer |
| Per-plugin config pages | Task 10 — PluginConfigPage |
| Core settings (DB, RAG, LLM, JWT) | Task 10 — CoreSettingsForm |
| Monitors CRUD | Task 9 |
| Jobs list | Task 5 (Jobs.tsx) |
| Mobile responsive | Tailwind + flex layout scales down |

**Placeholder scan:** None found.

**Type consistency:** `JobOut`, `MonitorOut`, `PluginInfo` defined once in `api/v3.ts` and imported everywhere. `WsEvent` defined once in `useWebSocket.ts`. `ThemeMode` in `lib/theme.ts`.
