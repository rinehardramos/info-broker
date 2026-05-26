import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import AuthGuard from './components/AuthGuard'
import Login from './pages/Login'
import AuthCallback from './pages/AuthCallback'
import { useLayoutStore } from './stores/layoutStore'
import { applyTheme } from './lib/theme'
import { ResultDrawer } from './components/runs/ResultDrawer'
import { PageShellSkeleton } from './components/ui/page-shell-skeleton'
import { queryClient as qc } from './lib/queryClient'
import { installCrossTabLogoutListener } from './lib/clearClientSession'

// Lazy-load pages to keep initial bundle small
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Research = lazy(() => import('./pages/Research'))
const Monitors  = lazy(() => import('./pages/Monitors'))
const Settings    = lazy(() => import('./pages/Settings'))
const LinkedInPage = lazy(() => import('./pages/LinkedInPage'))
const PluginsPage    = lazy(() => import('./pages/PluginsPage'))
const NodePluginPage = lazy(() => import('./pages/NodePluginPage'))
const PipelinePage   = lazy(() => import('./pages/PipelinePage'))
const LiveProcessesPage = lazy(() => import('./pages/LiveProcessesPage'))
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraphPage'))
const PerformanceDashboardPage = lazy(() => import('./pages/PerformanceDashboardPage'))
const AdminUsersPage = lazy(() => import('./pages/AdminUsersPage'))
const BenchmarkReportsPage = lazy(() => import('./pages/BenchmarkReportsPage'))
const AssetsPage = lazy(() => import('./pages/AssetsPage'))
const Wallet = lazy(() => import('./pages/Wallet'))
const Runs = lazy(() => import('./pages/Runs'))
const SharedRunPage = lazy(() => import('./pages/SharedRunPage'))

export default function App() {
  const theme = useLayoutStore(s => s.theme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => installCrossTabLogoutListener(), [])

  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<PageShellSkeleton />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/" element={<AuthGuard><Dashboard /></AuthGuard>} />
            <Route path="/dashboard" element={<AuthGuard><Dashboard /></AuthGuard>} />
            <Route path="/research" element={<AuthGuard><Research /></AuthGuard>} />
            {/* /jobs and /history redirect to the unified /runs page */}
            <Route path="/jobs" element={<Navigate to="/runs" replace />} />
            <Route path="/monitors" element={<AuthGuard><Monitors /></AuthGuard>} />
            <Route path="/history" element={<Navigate to="/runs" replace />} />
            <Route path="/runs" element={<AuthGuard><Runs /></AuthGuard>} />
            <Route path="/wallet" element={<AuthGuard><Wallet /></AuthGuard>} />
            <Route path="/assets" element={<AuthGuard><AssetsPage /></AuthGuard>} />
            <Route path="/linkedin" element={<AuthGuard><LinkedInPage /></AuthGuard>} />
            <Route path="/plugins" element={<AuthGuard><PluginsPage /></AuthGuard>} />
            <Route path="/plugins/node/:nodeType" element={<AuthGuard><NodePluginPage /></AuthGuard>} />
            <Route path="/pipelines" element={<AuthGuard><PipelinePage /></AuthGuard>} />
            <Route path="/pipelines/:id" element={<AuthGuard><PipelinePage /></AuthGuard>} />
            <Route path="/settings" element={<AuthGuard><Settings /></AuthGuard>} />
            <Route path="/settings/plugins/:name" element={<AuthGuard><Settings /></AuthGuard>} />
            <Route path="/admin/processes" element={<AuthGuard><LiveProcessesPage /></AuthGuard>} />
            <Route path="/admin/users" element={<AuthGuard><AdminUsersPage /></AuthGuard>} />
            <Route path="/admin/benchmarks" element={<AuthGuard><BenchmarkReportsPage /></AuthGuard>} />
            <Route path="/knowledge" element={<AuthGuard><KnowledgeGraphPage /></AuthGuard>} />
            <Route path="/performance" element={<AuthGuard><PerformanceDashboardPage /></AuthGuard>} />
            {/* Public share route — NO auth guard */}
            <Route path="/share/:token" element={<SharedRunPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
        <ResultDrawer />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
