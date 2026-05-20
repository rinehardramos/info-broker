import { useEffect, useState, FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  getMe, changePassword, setPassword, updateProfile,
  type MeResponse,
} from '@/api/auth'
import { Skeleton } from '@/components/ui/skeleton'
import { InlineError } from '@/components/ui/inline-error'

type Status = { kind: 'ok' | 'err'; text: string } | null

function StatusLine({ status }: { status: Status }) {
  if (!status) return null
  const color = status.kind === 'ok' ? '#22c55e' : '#ef4444'
  return <p className="text-xs mt-2" style={{ color }}>{status.text}</p>
}

export default function AccountSection() {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    getMe()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) {
    return (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
      </div>
    )
  }
  if (!me) {
    return (
      <InlineError
        title="Couldn't load account"
        onRetry={() => setRefreshKey(k => k + 1)}
      />
    )
  }

  return (
    <div className="flex flex-col gap-4 max-w-xl">
      <ProfileCard me={me} onSaved={() => setRefreshKey(k => k + 1)} />
      {me.password_set
        ? <ChangePasswordCard />
        : <SetPasswordCard onChanged={() => setRefreshKey(k => k + 1)} />}
    </div>
  )
}

function ProfileCard({ me, onSaved }: { me: MeResponse; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState(me.display_name ?? '')
  const [avatarUrl,   setAvatarUrl]   = useState(me.avatar_url ?? '')
  const [timezone,    setTimezone]    = useState(me.timezone ?? '')
  const [locale,      setLocale]      = useState(me.locale ?? '')
  const [busy,        setBusy]        = useState(false)
  const [status,      setStatus]      = useState<Status>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setStatus(null)
    try {
      await updateProfile({
        display_name: displayName,
        avatar_url:   avatarUrl,
        timezone:     timezone,
        locale:       locale,
      })
      setStatus({ kind: 'ok', text: 'Saved.' })
      onSaved()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setStatus({ kind: 'err', text: err?.response?.data?.detail ?? 'Could not save.' })
    } finally {
      setBusy(false)
    }
  }

  function detectTimezone() {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
      if (tz) setTimezone(tz)
    } catch { /* no-op */ }
  }
  function detectLocale() {
    try {
      const loc = navigator.language || (navigator.languages && navigator.languages[0])
      if (loc) setLocale(loc)
    } catch { /* no-op */ }
  }

  return (
    <Card style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
      <CardHeader>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Profile</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--muted)' }}>
          How you appear in the app. None of these affect sign-in.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          {avatarUrl && (
            <div className="flex items-center gap-3 mb-1">
              <img
                src={avatarUrl}
                alt="avatar preview"
                width={48}
                height={48}
                style={{ borderRadius: 24, border: '1px solid var(--border)' }}
                onError={(ev) => { (ev.target as HTMLImageElement).style.display = 'none' }}
              />
              <span className="text-xs" style={{ color: 'var(--muted)' }}>Avatar preview</span>
            </div>
          )}
          <label className="text-xs" style={{ color: 'var(--muted)' }}>Display name</label>
          <Input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder={me.username} />
          <label className="text-xs mt-1" style={{ color: 'var(--muted)' }}>Avatar URL</label>
          <Input value={avatarUrl} onChange={e => setAvatarUrl(e.target.value)} placeholder="https://…/me.png" />
          <label className="text-xs mt-1" style={{ color: 'var(--muted)' }}>Timezone (IANA, e.g. America/Los_Angeles)</label>
          <div className="flex gap-2">
            <Input value={timezone} onChange={e => setTimezone(e.target.value)} placeholder="UTC" />
            <Button type="button" size="sm" variant="outline" onClick={detectTimezone}
              style={{ borderColor: 'var(--border)', color: 'var(--text)', whiteSpace: 'nowrap' }}>
              Detect
            </Button>
          </div>
          <label className="text-xs mt-1" style={{ color: 'var(--muted)' }}>Locale (BCP-47, e.g. en-US)</label>
          <div className="flex gap-2">
            <Input value={locale} onChange={e => setLocale(e.target.value)} placeholder="en" />
            <Button type="button" size="sm" variant="outline" onClick={detectLocale}
              style={{ borderColor: 'var(--border)', color: 'var(--text)', whiteSpace: 'nowrap' }}>
              Detect
            </Button>
          </div>
          <Button type="submit" size="sm" disabled={busy} className="mt-2"
            style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}>
            {busy ? 'Saving…' : 'Save profile'}
          </Button>
          <StatusLine status={status} />
        </form>
      </CardContent>
    </Card>
  )
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<Status>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus(null)
    if (next !== confirm) { setStatus({ kind: 'err', text: 'New passwords do not match.' }); return }
    if (next.length < 12) { setStatus({ kind: 'err', text: 'New password must be at least 12 characters.' }); return }
    setBusy(true)
    try {
      await changePassword(current, next)
      setStatus({ kind: 'ok', text: 'Password changed.' })
      setCurrent(''); setNext(''); setConfirm('')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setStatus({ kind: 'err', text: err?.response?.data?.detail ?? 'Could not change password.' })
    } finally { setBusy(false) }
  }

  return (
    <Card style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
      <CardHeader>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Change password</h3>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <Input type="password" placeholder="Current password" value={current}
            onChange={e => setCurrent(e.target.value)} autoComplete="current-password" />
          <Input type="password" placeholder="New password (min 12)" value={next}
            onChange={e => setNext(e.target.value)} autoComplete="new-password" />
          <Input type="password" placeholder="Confirm new password" value={confirm}
            onChange={e => setConfirm(e.target.value)} autoComplete="new-password" />
          <Button type="submit" size="sm" disabled={busy}
            style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}>
            {busy ? 'Saving…' : 'Change password'}
          </Button>
          <StatusLine status={status} />
        </form>
      </CardContent>
    </Card>
  )
}

function SetPasswordCard({ onChanged }: { onChanged: () => void }) {
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<Status>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus(null)
    if (next !== confirm) { setStatus({ kind: 'err', text: 'Passwords do not match.' }); return }
    if (next.length < 12) { setStatus({ kind: 'err', text: 'Password must be at least 12 characters.' }); return }
    setBusy(true)
    try {
      await setPassword(next)
      setStatus({ kind: 'ok', text: 'Password set. You can now sign in with username + password.' })
      setNext(''); setConfirm('')
      onChanged()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setStatus({ kind: 'err', text: err?.response?.data?.detail ?? 'Could not set password.' })
    } finally { setBusy(false) }
  }

  return (
    <Card style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}>
      <CardHeader>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Set password</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--muted)' }}>
          You signed in with Google. Set a password to enable password login as a backup.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <Input type="password" placeholder="New password (min 12)" value={next}
            onChange={e => setNext(e.target.value)} autoComplete="new-password" />
          <Input type="password" placeholder="Confirm new password" value={confirm}
            onChange={e => setConfirm(e.target.value)} autoComplete="new-password" />
          <Button type="submit" size="sm" disabled={busy}
            style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}>
            {busy ? 'Saving…' : 'Set password'}
          </Button>
          <StatusLine status={status} />
        </form>
      </CardContent>
    </Card>
  )
}
