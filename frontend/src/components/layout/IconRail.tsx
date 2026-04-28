import { useNavigate, useLocation } from 'react-router-dom'
import { useTheme } from '../../hooks/useTheme'
import { useSessionStore } from '../../stores/sessionStore'
import { THEMES } from '../../lib/theme'

const NAV = [
  { icon: '⬡', path: '/',         label: 'Research' },
  { icon: '◉', path: '/jobs',     label: 'Jobs' },
  { icon: '◈', path: '/monitors', label: 'Monitors' },
  { icon: '▤', path: '/history',  label: 'History' },
  { icon: '⚙', path: '/settings', label: 'Settings' },
]

export default function IconRail() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { theme, toggle } = useTheme()
  const { logout, username } = useSessionStore()

  return (
    <div
      className="flex flex-col items-center py-3 gap-4 flex-shrink-0"
      style={{
        width: 28,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--border)',
      }}
    >
      <span style={{ color: 'var(--accent)', fontSize: 11 }}>✦</span>

      <div className="flex-1 flex flex-col items-center gap-3 mt-2">
        {NAV.map(({ icon, path, label }) => {
          const active = location.pathname === path
          return (
            <button
              key={path}
              title={label}
              onClick={() => navigate(path)}
              style={{
                width: 20,
                height: 20,
                fontSize: 11,
                color: active ? 'var(--accent)' : 'var(--muted)',
                background: active ? 'var(--panel2)' : 'transparent',
                cursor: 'pointer',
                border: 'none',
                borderRadius: 3,
              }}
            >
              {icon}
            </button>
          )
        })}
      </div>

      <div className="flex flex-col items-center gap-3">
        <button
          title={`Switch to ${theme === 'navy' ? 'Hacker' : 'Deep Navy'}`}
          onClick={toggle}
          style={{ fontSize: 10, color: 'var(--subtext)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          {THEMES[theme].icon}
        </button>
        <button
          title={`Logged in as ${username ?? '…'} (click to logout)`}
          onClick={logout}
          style={{
            width: 18, height: 18, borderRadius: '50%',
            background: 'var(--accent)', color: 'var(--bg)',
            fontSize: 9, fontWeight: 'bold', border: 'none', cursor: 'pointer',
          }}
        >
          {(username?.[0] ?? 'U').toUpperCase()}
        </button>
      </div>
    </div>
  )
}
