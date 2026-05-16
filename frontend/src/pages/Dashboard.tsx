import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import IconRail from '@/components/layout/IconRail'
import { StatCard } from '@/components/dashboard/StatCard'
import { RunListTable } from '@/components/runs/RunListTable'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { listRuns, getRunMetrics } from '@/api/v3'

export default function Dashboard() {
  const navigate = useNavigate()
  const openDrawer = useResultDrawerStore((s) => s.open)

  const { data: metrics } = useQuery({
    queryKey: ['run-metrics'],
    queryFn: getRunMetrics,
    refetchInterval: 30_000,
  })

  const { data: runs } = useQuery({
    queryKey: ['recent-runs'],
    queryFn: listRuns,
    refetchInterval: 30_000,
  })

  const recent = (runs ?? [])
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 20)

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-6">
        <h1 className="text-lg font-semibold">Dashboard</h1>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Runs Today" value={metrics?.runs_today ?? '—'} sub="since 00:00 local" />
          <StatCard
            title="Success Rate"
            value={metrics ? `${Math.round((metrics.success_rate ?? 0) * 100)}%` : '—'}
            sub="last 7 days"
          />
          <StatCard title="Live" value={metrics?.live_runs ?? '—'} sub="currently running" />
          <StatCard
            title="Errors"
            value={metrics?.error_count ?? '—'}
            sub="last 24 h"
            emphasis={(metrics?.error_count ?? 0) > 0 ? 'danger' : 'normal'}
          />
        </div>

        <section className="space-y-2">
          <h2 className="text-sm font-semibold opacity-70">Recent runs</h2>
          <RunListTable
            rows={recent}
            onShow={openDrawer}
            onRerun={(query) => navigate(`/research?q=${encodeURIComponent(query)}`)}
          />
        </section>
      </div>
      <IconRail />
    </div>
  )
}
