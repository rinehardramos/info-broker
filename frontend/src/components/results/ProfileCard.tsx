interface Profile {
  id: string
  first_name?: string
  last_name?: string
  headline?: string
  about?: string
}

export default function ProfileCard({ profile }: { profile: Profile }) {
  const name = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || '—'
  return (
    <div
      className="p-3 rounded mb-2 text-xs"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{name}</div>
      {profile.headline && (
        <div className="mb-1 truncate" style={{ color: 'var(--subtext)' }}>{profile.headline}</div>
      )}
      {profile.about && (
        <div className="line-clamp-3" style={{ color: 'var(--muted)' }}>{profile.about}</div>
      )}
    </div>
  )
}
