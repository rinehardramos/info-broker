import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useSessionStore(s => s.accessToken)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}
