import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTheme } from '../../hooks/useTheme'
import { useSessionStore } from '../../stores/sessionStore'
import { THEMES } from '../../lib/theme'
import {
  LayoutDashboard,
  Search,
  Radio,
  Puzzle,
  Settings,
  Users,
  Gauge,
  Activity,
  Wallet,
  List,
  FolderOpen,
} from 'lucide-react'
import { listPluginRequests } from '../../api/pipelines'
import { LogoMark } from '@/components/brand/LogoMark'

const NAV = [
  { icon: <LayoutDashboard size={18} />, path: '/dashboard', label: 'Dashboard' },
  { icon: <Search size={18} />,          path: '/research',  label: 'Research' },
  { icon: <Radio size={18} />,           path: '/monitors',  label: 'Monitors' },
  // History is the unified run log (filters + cost column).
  // /history and /jobs both redirect to /runs in App.tsx.
  { icon: <List size={18} />,            path: '/runs',      label: 'History' },
  { icon: <Wallet size={18} />,          path: '/wallet',    label: 'Wallet' },
  { icon: <FolderOpen size={18} />,      path: '/assets',    label: 'Assets' },
  { icon: <Puzzle size={18} />,          path: '/plugins',   label: 'Plugins' },
]

// Admin-only — rendered only when isAdmin, after NAV and before Settings.
const NAV_ADMIN = [
  { icon: <Users size={18} />,    path: '/admin/users',      label: 'User Management' },
  { icon: <Gauge size={18} />,    path: '/admin/benchmarks', label: 'Benchmark Reports' },
  { icon: <Activity size={18} />, path: '/admin/monitoring', label: 'Monitoring' },
]

// Settings always sits last in the rail, after any admin items.
const NAV_SETTINGS = { icon: <Settings size={18} />, path: '/settings', label: 'Settings' }

const RAIL_W = 52
const BTN_SIZE = 40

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

  const allNav = [...NAV, ...(isAdmin ? NAV_ADMIN : []), NAV_SETTINGS]

  return (
    <div
      className="flex flex-col items-center py-4 flex-shrink-0"
      style={{
        width: RAIL_W,
        background: 'var(--panel)',
        borderLeft: '1px solid var(--border)',
        gap: 0,
      }}
    >
      {/* Logo mark — home button */}
      <button
        title="infobroker"
        onClick={() => navigate('/dashboard')}
        style={{
          width: BTN_SIZE,
          height: BTN_SIZE,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'transparent',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
          marginBottom: 8,
          flexShrink: 0,
        }}
      >
        <LogoMark size={28} />
      </button>

      {/* Divider */}
      <div style={{ width: 28, height: 1, background: 'var(--border)', marginBottom: 8, flexShrink: 0 }} />

      {/* Nav items */}
      <div className="flex-1 flex flex-col items-center overflow-hidden" style={{ gap: 4, width: '100%', paddingInline: 6 }}>
        {allNav.map(({ icon, path, label }) => {
          const active = location.pathname === path || location.pathname.startsWith(path + '/')
          const hasBadge = path === '/plugins' && pendingCount > 0
          return (
            <button
              key={path}
              title={hasBadge ? `${label} (${pendingCount} pending)` : label}
              onClick={() => navigate(path)}
              style={{
                width: BTN_SIZE,
                height: BTN_SIZE,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                background: active ? 'rgba(167,139,250,0.14)' : 'transparent',
                color: active ? '#a78bfa' : 'var(--muted)',
                border: active ? '1px solid rgba(167,139,250,0.25)' : '1px solid transparent',
                borderRadius: 8,
                cursor: 'pointer',
                position: 'relative',
                transition: 'background 0.12s, color 0.12s',
              }}
              onMouseEnter={e => {
                if (!active) {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.05)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--subtext)'
                }
              }}
              onMouseLeave={e => {
                if (!active) {
                  (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--muted)'
                }
              }}
            >
              {icon}
              {hasBadge && (
                <span style={{
                  position: 'absolute', top: 6, right: 6,
                  width: 7, height: 7, borderRadius: '50%',
                  background: '#f87171', border: '1px solid var(--panel)',
                }} />
              )}
            </button>
          )
        })}
      </div>

      {/* Bottom controls */}
      <div className="flex flex-col items-center" style={{ gap: 4, paddingInline: 6, paddingTop: 8 }}>
        <button
          title={`Switch to ${theme === 'navy' ? 'Hacker' : 'Deep Navy'}`}
          onClick={toggle}
          style={{
            width: BTN_SIZE,
            height: BTN_SIZE,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 15,
            color: 'var(--subtext)',
            background: 'transparent',
            border: '1px solid transparent',
            borderRadius: 8,
            cursor: 'pointer',
          }}
        >
          {THEMES[theme].icon}
        </button>
        <button
          title={`${username ?? '…'} — click to logout`}
          onClick={logout}
          style={{
            width: BTN_SIZE,
            height: BTN_SIZE,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 8,
            background: 'rgba(167,139,250,0.18)',
            border: '1px solid rgba(167,139,250,0.3)',
            color: '#a78bfa',
            fontSize: 12,
            fontWeight: 700,
            cursor: 'pointer',
            letterSpacing: '0.05em',
          }}
        >
          {(username?.[0] ?? 'U').toUpperCase()}
        </button>
      </div>
    </div>
  )
}
