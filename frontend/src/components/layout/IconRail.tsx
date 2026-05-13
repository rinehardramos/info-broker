import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTheme } from '../../hooks/useTheme'
import { useSessionStore } from '../../stores/sessionStore'
import { THEMES } from '../../lib/theme'
import { listPluginRequests } from '../../api/pipelines'

const NAV = [
  { icon: '⬡', path: '/',          label: 'Research' },
  { icon: '◉', path: '/jobs',      label: 'Jobs' },
  { icon: '◈', path: '/monitors',  label: 'Monitors' },
  { icon: '▤', path: '/history',   label: 'History' },
  { icon: '❖', path: '/plugins',   label: 'Plugins' },
  { icon: '◎', path: '/admin/processes', label: 'Live Processes' },
  { icon: '⬢', path: '/knowledge',       label: 'Knowledge Graph' },
  { icon: '▦', path: '/performance',     label: 'Performance Dashboard' },
  { icon: '⚙', path: '/settings',  label: 'Settings' },
]

const NAV_ADMIN = [
  { icon: '◫', path: '/admin/users', label: 'User Management' },
]

export default function IconRail() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { theme, toggle } = useTheme()
  const { logout, username, isAdmin } = useSessionStore()

  const { data: pluginRequests } = useQuery({
    queryKey: ['plugin-requests'],
    queryFn: listPluginRequests,
    refetchInterval: 30000,
  })
  const pendingCount = pluginRequests?.filter(r => r.status === 'pending').length ?? 0

  const allNav = isAdmin ? [...NAV, ...NAV_ADMIN] : NAV

  return (
    <div
      className="flex flex-col items-center py-3 gap-4 flex-shrink-0"
      style={{
        width: 36,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--border)',
      }}
    >
      <span style={{ color: 'var(--accent)', fontSize: 14 }}>✦</span>

      <div className="flex-1 flex flex-col items-center gap-3 mt-2">
        {allNav.map(({ icon, path, label }) => {
          const active = location.pathname === path
          const hasBadge = path === '/plugins' && pendingCount > 0
          return (
            <button
              key={path}
              title={hasBadge ? `${label} (${pendingCount} pending)` : label}
              onClick={() => navigate(path)}
              style={{
                width: 26,
                height: 26,
                fontSize: 14,
                color: active ? 'var(--accent)' : 'var(--muted)',
                background: active ? 'var(--panel2)' : 'transparent',
                cursor: 'pointer',
                border: 'none',
                borderRadius: 4,
                position: 'relative',
              }}
            >
              {icon}
              {hasBadge && (
                <span style={{
                  position: 'absolute', top: -2, right: -4,
                  width: 8, height: 8, borderRadius: '50%',
                  background: '#f87171', border: '1px solid var(--panel)',
                }} />
              )}
            </button>
          )
        })}
      </div>

      <div className="flex flex-col items-center gap-3">
        <button
          title={`Switch to ${theme === 'navy' ? 'Hacker' : 'Deep Navy'}`}
          onClick={toggle}
          style={{ fontSize: 13, color: 'var(--subtext)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          {THEMES[theme].icon}
        </button>
        <button
          title={`Logged in as ${username ?? '…'} (click to logout)`}
          onClick={logout}
          style={{
            width: 22, height: 22, borderRadius: '50%',
            background: 'var(--accent)', color: 'var(--bg)',
            fontSize: 10, fontWeight: 'bold', border: 'none', cursor: 'pointer',
          }}
        >
          {(username?.[0] ?? 'U').toUpperCase()}
        </button>
      </div>
    </div>
  )
}
