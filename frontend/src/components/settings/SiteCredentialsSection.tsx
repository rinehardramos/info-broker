import { useState, useEffect, useCallback } from 'react'
import { storeSiteCredential, listSiteCredentials, type SiteCredentialEntry } from '../../api/v3'

/**
 * Site Logins (authenticated-session vault, #item-4). Lets a user store their
 * OWN login for a site (e.g. fsbo.com, an MLS/IDX portal) so the stealth browser
 * can log in and access data gated behind that account. The password is
 * encrypted at rest, never returned by any endpoint, and never reaches the brain
 * (resolved server-side only). The user is responsible for ensuring they're
 * authorized to automate access per the site's terms.
 */
export default function SiteCredentialsSection() {
  const [entries, setEntries] = useState<SiteCredentialEntry[]>([])
  const [site, setSite] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const refresh = useCallback(() => {
    listSiteCredentials().then(setEntries).catch(() => setEntries([]))
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    if (!site.trim() || !username.trim() || !password) return
    setSaving(true); setError(null); setSaved(false)
    try {
      await storeSiteCredential(site.trim().toLowerCase(), username.trim(), password, 'user')
      setSaved(true); setPassword(''); refresh()
    } catch {
      setError('Failed to save credential. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = {
    flex: 1, fontSize: 12, padding: '5px 8px', borderRadius: 4,
    background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)',
  } as const

  return (
    <div style={{ maxWidth: 560 }}>
      <p className="text-xs" style={{ color: 'var(--subtext)', lineHeight: 1.6, marginBottom: 12 }}>
        Store a login for a site you have an account on (e.g. <code>fsbo.com</code>, an MLS/IDX portal).
        The stealth browser uses it to access data gated behind that account. Your password is
        encrypted at rest, is never shown again, and never reaches the research brain. Only store
        credentials for accounts you own and are permitted to automate per the site&apos;s terms.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
        <input data-testid="sitecred-site" style={inputStyle} placeholder="site (e.g. fsbo.com)"
          value={site} onChange={e => setSite(e.target.value)} autoComplete="off" />
        <input data-testid="sitecred-username" style={inputStyle} placeholder="username / email"
          value={username} onChange={e => setUsername(e.target.value)} autoComplete="off" />
        <div style={{ display: 'flex', gap: 6 }}>
          <input data-testid="sitecred-password" type="password" style={inputStyle} placeholder="password"
            value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" />
          <button
            onClick={save}
            disabled={saving || !site.trim() || !username.trim() || !password}
            data-testid="sitecred-save"
            style={{
              fontSize: 12, padding: '5px 14px', borderRadius: 4, border: 'none',
              background: 'var(--accent)', color: '#fff',
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: (saving || !site.trim() || !username.trim() || !password) ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving…' : 'Save login'}
          </button>
        </div>
        {error && <span className="text-[11px]" style={{ color: '#f87171' }}>{error}</span>}
        {saved && <span className="text-[11px]" style={{ color: '#34d399' }} data-testid="sitecred-saved">✓ Login saved (encrypted)</span>}
      </div>

      <div className="text-[10px] font-semibold mb-2" style={{ color: 'var(--muted)' }}>SAVED LOGINS</div>
      {entries.length === 0 ? (
        <p className="text-[11px]" style={{ color: 'var(--subtext)' }}>No site logins stored yet.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {entries.map(e => (
            <div key={`${e.scope}:${e.site}`} data-testid={`sitecred-row-${e.site}`}
              className="flex items-center gap-2 text-[11px] px-2 py-1 rounded"
              style={{ background: 'var(--panel)', border: '1px solid var(--border)', color: 'var(--text)' }}>
              <span style={{ fontWeight: 600 }}>{e.site}</span>
              <span style={{ color: 'var(--subtext)' }}>{e.username}</span>
              <span className="ml-auto text-[10px] px-2 py-0.5 rounded"
                style={{ background: 'var(--panel2)', color: 'var(--subtext)' }}>{e.scope}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
