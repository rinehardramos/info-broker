import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { useSessionStore } from '../stores/sessionStore'
import { Logo } from '@/components/brand/Logo'

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
        <div className="mb-4">
          <Logo size="md" variant="dark" />
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
        {error && <span className="text-xs" style={{ color: '#ef4444' }}>{error}</span>}
        <button
          type="submit"
          disabled={loading}
          className="px-3 py-2 rounded text-sm font-semibold disabled:opacity-50"
          style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
