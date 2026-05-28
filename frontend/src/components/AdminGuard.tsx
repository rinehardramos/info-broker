import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'
import AuthGuard from './AuthGuard'

// Gates admin-only routes (/admin/*). Wraps AuthGuard for the auth check +
// profile hydration, then additionally redirects authenticated non-admins to
// the dashboard. `isAdmin` is derived synchronously from the JWT claims in
// sessionStore, so this is reliable even on a cold deep-link straight to an
// /admin route — the sidebar already hides these, this closes the direct-URL hole.
export default function AdminGuard({ children }: { children: ReactNode }) {
  const isAdmin = useSessionStore(s => s.isAdmin)
  return (
    <AuthGuard>
      {isAdmin ? <>{children}</> : <Navigate to="/dashboard" replace />}
    </AuthGuard>
  )
}
