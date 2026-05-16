import { useEffect, useState, useCallback } from 'react'
import { getDashboardMetrics, getToolStats, DashboardMetrics } from '../../api/v3'

interface ToolStat {
  tool_name: string
  total_calls: number
  succeeded: number
  failed: number
  avg_duration_ms: number
  last_used: string
}

function MetricCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      className="flex flex-col gap-1 px-4 py-3 rounded"
      style={{ background: 'var(--panel)', border: '1px solid var(--border)' }}
    >
      <span className="text-[10px] font-medium" style={{ color: 'var(--muted)' }}>{label}</span>
      <span
        className="text-xl font-semibold"
        style={{ color: highlight ? 'var(--danger)' : 'var(--text)' }}
      >
        {value}
      </span>
    </div>
  )
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [toolStats, setToolStats] = useState<ToolStat[]>([])

  const fetchAll = useCallback(async () => {
    try {
      const [m, t] = await Promise.all([getDashboardMetrics(), getToolStats()])
      setMetrics(m)
      setToolStats(t)
    } catch {
      // silently ignore poll errors
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const errLastHour = metrics?.error_rate_last_hour
  const elhTotal = Number(errLastHour?.total)
  const elhErrors = Number(errLastHour?.errors)
  const errorRate =
    Number.isFinite(elhTotal) && elhTotal > 0 && Number.isFinite(elhErrors)
      ? (elhErrors / elhTotal) * 100
      : null
  const errorRateStr = errorRate != null ? `${errorRate.toFixed(1)}%` : '—'

  const avgDurationStr =
    metrics && metrics.avg_duration_ms != null
      ? `${Math.round(metrics.avg_duration_ms)}ms`
      : '—'

  return (
    <div className="flex flex-col gap-5 p-4 overflow-auto">
      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard label="Active Sessions" value={metrics ? String(metrics.active_sessions) : '—'} />
        <MetricCard label="Total Tool Calls" value={metrics ? String(metrics.total_tool_calls) : '—'} />
        <MetricCard
          label="Error Rate (1h)"
          value={errorRateStr}
          highlight={(errorRate ?? 0) > 10}
        />
        <MetricCard label="Avg Duration" value={avgDurationStr} />
      </div>

      {/* Top tools table */}
      <div>
        <div
          className="px-3 py-2 text-[11px] font-semibold"
          style={{ color: 'var(--muted)', borderBottom: '1px solid var(--border)' }}
        >
          Top Tools (24h)
        </div>
        {toolStats.length === 0 ? (
          <div className="px-3 py-4 text-xs" style={{ color: 'var(--muted)' }}>No tool stats available.</div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Tool</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Calls</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Succeeded</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Failed</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Avg Duration</th>
              </tr>
            </thead>
            <tbody>
              {toolStats.map(t => (
                <tr key={t.tool_name} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-3 py-1.5" style={{ color: 'var(--text)' }}>{t.tool_name}</td>
                  <td className="px-3 py-1.5 text-right" style={{ color: 'var(--text)' }}>{t.total_calls}</td>
                  <td className="px-3 py-1.5 text-right" style={{ color: '#4ade80' }}>{t.succeeded}</td>
                  <td
                    className="px-3 py-1.5 text-right"
                    style={{ color: t.failed > 0 ? 'var(--danger)' : 'var(--muted)' }}
                  >
                    {t.failed}
                  </td>
                  <td className="px-3 py-1.5 text-right" style={{ color: 'var(--muted)' }}>
                    {t.avg_duration_ms != null ? `${Math.round(t.avg_duration_ms)}ms` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
