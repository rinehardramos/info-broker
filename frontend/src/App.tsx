import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AuthGuard from './components/AuthGuard'
import Login from './pages/Login'
import { useLayoutStore } from './stores/layoutStore'
import { applyTheme } from './lib/theme'

// Lazy-load pages to keep initial bundle small
const Research = lazy(() => import('./pages/Research'))
const Jobs      = lazy(() => import('./pages/Jobs'))
const Monitors  = lazy(() => import('./pages/Monitors'))
const History   = lazy(() => import('./pages/History'))
const Settings    = lazy(() => import('./pages/Settings'))
const LinkedInPage = lazy(() => import('./pages/LinkedInPage'))

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', color: 'var(--muted)', fontSize: 12 }}>
      loading…
    </div>
  )
}

export default function App() {
  const theme = useLayoutStore(s => s.theme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<Spinner />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<AuthGuard><Research /></AuthGuard>} />
            <Route path="/jobs" element={<AuthGuard><Jobs /></AuthGuard>} />
            <Route path="/monitors" element={<AuthGuard><Monitors /></AuthGuard>} />
            <Route path="/history" element={<AuthGuard><History /></AuthGuard>} />
            <Route path="/linkedin" element={<AuthGuard><LinkedInPage /></AuthGuard>} />
            <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
            <Route path="/settings/plugins/:name" element={<AuthGuard><Settings /></AuthGuard>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
