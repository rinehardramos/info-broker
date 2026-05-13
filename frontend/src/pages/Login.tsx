import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { useSessionStore } from '../stores/sessionStore'
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
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: 'var(--bg)' }}
    >
      <Card className="w-full max-w-sm border" style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
        <CardHeader className="items-center pb-2 pt-8">
          <Logo size="md" variant="dark" />
          <p className="text-xs mt-3 text-center" style={{ color: 'var(--muted)' }}>
            Sign in to your workspace
          </p>
        </CardHeader>

        <CardContent className="pb-8">
          {/* Social login placeholders */}
          <div className="flex flex-col gap-2 mb-5">
            <Button
              type="button"
              variant="outline"
              className="w-full gap-2 text-sm"
              style={{ borderColor: 'var(--border)', color: 'var(--subtext)', background: 'transparent' }}
              disabled
              title="Google login — coming soon"
            >
              <GoogleIcon />
              Continue with Google
            </Button>
            <Button
              type="button"
              variant="outline"
              className="w-full gap-2 text-sm"
              style={{ borderColor: 'var(--border)', color: 'var(--subtext)', background: 'transparent' }}
              disabled
              title="GitHub login — coming soon"
            >
              <GithubIcon />
              Continue with GitHub
            </Button>
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
              className="text-sm"
              style={{ background: 'var(--panel2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />
            <Input
              type="password"
              name="password"
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              className="text-sm"
              style={{ background: 'var(--panel2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />

            {error && (
              <p className="text-xs" style={{ color: '#ef4444' }}>{error}</p>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full text-sm font-semibold mt-1"
              style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
