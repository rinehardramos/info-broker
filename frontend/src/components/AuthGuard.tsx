import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'
import { getMe } from '../api/v3'

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useSessionStore(s => s.accessToken)
  const { setUser, userId } = useSessionStore()

  // Hydrate user profile (username, isAdmin) once per session — not per page.
  // Placed here so it runs regardless of which authenticated page loads first.
  useEffect(() => {
    if (!token || userId) return
    getMe()
      .then(user => setUser(user.id, user.username, user.is_admin))
      .catch(() => {})
  }, [token, userId, setUser])

  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}
