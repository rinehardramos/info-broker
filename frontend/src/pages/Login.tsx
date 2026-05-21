import { useState, useEffect, useRef, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { api } from '@/api/client'

// Google Identity Services types (loaded via script tag, see useEffect below)
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (resp: { credential: string }) => void
            auto_select?: boolean
            cancel_on_tap_outside?: boolean
          }) => void
          renderButton: (
            el: HTMLElement,
            opts: { theme?: 'outline' | 'filled_blue' | 'filled_black'; size?: 'small' | 'medium' | 'large'; width?: number; type?: 'standard' | 'icon'; shape?: 'rectangular' | 'pill' | 'circle' | 'square'; text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin' },
          ) => void
          prompt: () => void
        }
      }
    }
  }
}
import { Logo } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Card, CardContent, CardHeader } from '@/components/ui/card'

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}

function GithubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>
  )
}

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const navigate                = useNavigate()
  const { setTokens }           = useSessionStore()
  const clearChat               = useChatStore(s => s.clearMessages)

  // Discover which SSO providers are configured on the backend so we can
  // disable buttons (and label them as "coming soon") when keys aren't set.
  const [providers, setProviders] = useState<{
    google: boolean
    github: boolean
    google_client_id?: string | null
  }>({ google: false, github: false, google_client_id: null })
  useEffect(() => {
    api.get('/v3/auth/providers')
      .then((r) => setProviders(r.data))
      .catch(() => { /* leave both disabled */ })
  }, [])

  // ---- Google One-Tap / "Sign in with Google" native button ----
  const gsiBtnRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!providers.google || !providers.google_client_id) return
    // Inject the GSI script once.
    const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]')
    let cleanup: (() => void) | undefined
    function initGsi() {
      const g = window.google
      const cid = providers.google_client_id
      if (!g || !cid) return
      g.accounts.id.initialize({
        client_id: cid,
        callback: async (resp) => {
          if (!resp?.credential) return
          try {
            const r = await api.post('/v3/auth/google/onetap', { credential: resp.credential })
            clearChat()
            setTokens(r.data.access_token, r.data.refresh_token)
            navigate('/')
          } catch (e: unknown) {
            const errResp = (e as { response?: { data?: { detail?: string } } })?.response
            setError(errResp?.data?.detail ?? 'Google sign-in failed')
          }
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      })
      if (gsiBtnRef.current) {
        g.accounts.id.renderButton(gsiBtnRef.current, {
          theme: 'filled_black',
          size: 'large',
          width: 320,
          shape: 'rectangular',
          text: 'continue_with',
        })
      }
      // Also show the One-Tap prompt at the top right (auto-skips if no Google session).
      g.accounts.id.prompt()
    }
    if (!existing) {
      const s = document.createElement('script')
      s.src = 'https://accounts.google.com/gsi/client'
      s.async = true
      s.defer = true
      s.onload = initGsi
      document.head.appendChild(s)
      cleanup = () => { s.remove() }
    } else {
      initGsi()
    }
    return cleanup
  }, [providers.google, providers.google_client_id, navigate, setTokens])

  function startOAuth(provider: 'google' | 'github') {
    // Full-page navigation — backend will 302 to the provider and back.
    // Used by the legacy redirect button (GitHub) + Google fallback.
    window.location.href = `/api/v3/auth/${provider}/login`
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const tokens = await login(username, password)
      clearChat()
      setTokens(tokens.access_token, tokens.refresh_token)
      navigate('/')
    } catch {
      setError('Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: 'var(--bg)' }}
    >
      <Card className="w-full max-w-sm border" style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
        <CardHeader className="items-center pb-2 pt-8">
          <Logo size="lg" variant="dark" />
          <p className="text-xs mt-3 text-center" style={{ color: 'var(--muted)' }}>
            Sign in to your workspace
          </p>
        </CardHeader>

        <CardContent className="pb-8">
          {/* Social login placeholders */}
          <div className="flex flex-col gap-2 mb-5">
            {providers.google && providers.google_client_id ? (
              // Google Identity Services renders its own button into this div
              // (filled-black, "Continue with Google", with the official logo).
              <div ref={gsiBtnRef} style={{ display: 'flex', justifyContent: 'center' }} />
            ) : (
              <Button
                type="button"
                variant="outline"
                onClick={() => startOAuth('google')}
                className="w-full gap-2 text-sm"
                style={{ borderColor: 'var(--border)', color: 'var(--subtext)', background: 'transparent' }}
                disabled
                title="Google login — not configured"
              >
                <GoogleIcon />
                Continue with Google
              </Button>
            )}
            <button
              type="button"
              onClick={() => startOAuth('github')}
              disabled={!providers.github}
              title={providers.github ? 'Continue with your GitHub account' : 'GitHub login — not configured'}
              className="w-full inline-flex items-center justify-center gap-2 text-sm font-semibold rounded-md px-4 py-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: '#24292e',
                color: '#ffffff',
                border: '1px solid #24292e',
                cursor: providers.github ? 'pointer' : 'not-allowed',
              }}
              onMouseEnter={e => { if (providers.github) e.currentTarget.style.background = '#1b1f23' }}
              onMouseLeave={e => { if (providers.github) e.currentTarget.style.background = '#24292e' }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 .5C5.65.5.5 5.65.5 12.02c0 5.1 3.29 9.42 7.86 10.95.57.1.78-.25.78-.55v-1.93c-3.2.7-3.87-1.54-3.87-1.54-.52-1.32-1.27-1.68-1.27-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.7 1.25 3.36.96.1-.74.4-1.25.73-1.54-2.55-.29-5.23-1.28-5.23-5.71 0-1.26.45-2.29 1.18-3.09-.12-.29-.51-1.46.11-3.04 0 0 .97-.31 3.18 1.18a11.04 11.04 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.62 1.58.23 2.75.11 3.04.74.8 1.18 1.83 1.18 3.09 0 4.43-2.69 5.41-5.25 5.7.41.36.78 1.07.78 2.16v3.2c0 .31.21.66.79.55C20.21 21.43 23.5 17.12 23.5 12.02 23.5 5.65 18.35.5 12 .5Z"/>
              </svg>
              Continue with GitHub
            </button>
          </div>

          <div className="flex items-center gap-3 mb-5">
            <Separator style={{ background: 'var(--border)', flex: 1 }} />
            <span className="text-xs" style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>
              or sign in with password
            </span>
            <Separator style={{ background: 'var(--border)', flex: 1 }} />
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <Input
              type="text"
              name="username"
              placeholder="Username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              className="text-sm h-12"
              style={{ background: 'var(--panel2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />
            <Input
              type="password"
              name="password"
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              className="text-sm h-12"
              style={{ background: 'var(--panel2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />

            {error && (
              <p className="text-xs" style={{ color: '#ef4444' }}>{error}</p>
            )}

            <Button
              type="submit"
              size="lg"
              disabled={loading}
              className="w-full font-semibold mt-1 text-base tracking-wide"
              style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none', height: 52 }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
