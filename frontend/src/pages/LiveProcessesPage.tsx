import { useState } from 'react'
import IconRail from '../components/layout/IconRail'
import SessionList from '../components/admin/SessionList'
import Dashboard from '../components/admin/Dashboard'

type Tab = 'sessions' | 'dashboard'

export default function LiveProcessesPage() {
  const [activeTab, setActiveTab] = useState<Tab>('sessions')

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      {/* Sidebar */}
      <div
        className="flex flex-col min-h-0 flex-1 overflow-hidden"
        style={{ borderRight: '1px solid var(--border)' }}
      >
        {/* Header with tab bar */}
        <div
          className="flex items-center gap-0 px-4 py-2 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}
        >
          <span className="text-xs font-semibold mr-4" style={{ color: 'var(--text)' }}>
            Live Processes
          </span>
          {(['sessions', 'dashboard'] as Tab[]).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-3 py-1 text-xs rounded capitalize"
              style={{
                background: activeTab === tab ? 'var(--accent)' : 'transparent',
                color: activeTab === tab ? 'var(--bg)' : 'var(--muted)',
                border: 'none',
                cursor: 'pointer',
                fontWeight: activeTab === tab ? 600 : 400,
              }}
            >
              {tab === 'sessions' ? 'Sessions' : 'Dashboard'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {activeTab === 'sessions' ? <SessionList /> : <Dashboard />}
        </div>
      </div>

      {/* Icon rail */}
      <IconRail />
    </div>
  )
}
