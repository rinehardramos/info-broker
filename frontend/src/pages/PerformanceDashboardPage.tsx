import IconRail from '../components/layout/IconRail'
import PerformanceDashboard from '../components/results/PerformanceDashboard'

export default function PerformanceDashboardPage() {
  return (
    <div
      className="flex h-screen"
      style={{ background: 'var(--bg)', color: 'var(--text)' }}
    >
      <div className="flex-1 flex flex-col overflow-hidden">
        <div
          className="px-4 py-3 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <h1 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            Performance Dashboard
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>
            Aggregate technique and tactic grades across all research runs
          </p>
        </div>
        <div className="flex-1 overflow-y-auto">
          <PerformanceDashboard />
        </div>
      </div>
      <IconRail />
    </div>
  )
}
