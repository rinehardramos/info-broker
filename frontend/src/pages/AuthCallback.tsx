import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSessionStore } from '../stores/sessionStore'

/**
 * /auth/callback — terminal of the OAuth round-trip.
 *
 * Backend redirects here with tokens in the URL fragment:
 *   /auth/callback#access_token=...&refresh_token=...
 *
 * The fragment is parsed, tokens are stored in sessionStore, and the user
 * is sent to the home page. Errors are shown with a "back to login" link.
 */
export default function AuthCallback() {
  const navigate = useNavigate()
  const { setTokens } = useSessionStore()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '')
    const params = new URLSearchParams(hash)
    const err = params.get('error')
    if (err) {
      setError(err)
      return
    }
    const access = params.get('access_token')
    const refresh = params.get('refresh_token')
    if (!access || !refresh) {
      setError('Missing token in callback URL')
      return
    }
    setTokens(access, refresh)
    // Clear the fragment so tokens don't linger in history.
    window.history.replaceState(null, '', '/')
    navigate('/', { replace: true })
  }, [navigate, setTokens])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--bg)' }}>
        <div className="max-w-md w-full p-6 rounded-xl border text-center" style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
          <h1 className="text-lg font-semibold mb-2" style={{ color: 'var(--text)' }}>Sign-in failed</h1>
          <p className="text-sm mb-5" style={{ color: 'var(--subtext)' }}>{error}</p>
          <a href="/login" className="text-sm underline" style={{ color: 'var(--accent)' }}>Back to login</a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="text-sm">Completing sign-in…</div>
    </div>
  )
}
