import { useState, FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import IconRail from '@/components/layout/IconRail'
import { StatCard } from '@/components/dashboard/StatCard'
import { RunListTable } from '@/components/runs/RunListTable'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { InlineError } from '@/components/ui/inline-error'
import { useDebouncedLoading } from '@/hooks/useDebouncedLoading'
import {
  listRuns, getRunMetrics, listPlugins, getWallet, getPerformanceDashboard,
  getWorkerHealth, listInvestigationTemplates, getUserCostAggregate,
  getOpenQuestionsDigest,
  type WorkerHealth, type InvestigationTemplate,
} from '@/api/v3'

export default function Dashboard() {
  const navigate = useNavigate()
  const openDrawer = useResultDrawerStore((s) => s.open)
  const [quickQuery, setQuickQuery] = useState('')
  const [templatesOpen, setTemplatesOpen] = useState(false)

  const { data: templates } = useQuery<InvestigationTemplate[]>({
    queryKey: ['investigation-templates'],
    queryFn: listInvestigationTemplates,
    staleTime: 24 * 60 * 60_000,    // built-in list rarely changes
    retry: false,
  })

  const { data: metrics } = useQuery({
    queryKey: ['run-metrics'],
    queryFn: getRunMetrics,
    refetchInterval: 30_000,
  })

  const {
    data: runs,
    isLoading: runsLoading,
    isError: runsError,
    error: runsErrorObj,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['recent-runs'],
    queryFn: listRuns,
    refetchInterval: 30_000,
  })

  const { data: plugins } = useQuery({
    queryKey: ['plugins-dashboard'],
    queryFn: listPlugins,
    staleTime: 5 * 60_000,
  })

  const { data: wallet } = useQuery({
    queryKey: ['wallet-dashboard'],
    queryFn: getWallet,
    refetchInterval: 60_000,
    retry: false,
  })

  const { data: perf } = useQuery({
    queryKey: ['perf-dashboard'],
    queryFn: getPerformanceDashboard,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: workerHealth } = useQuery({
    queryKey: ['worker-health'],
    queryFn: getWorkerHealth,
    refetchInterval: 30_000,
    retry: false,
  })
  const {
    data: costAgg,
    isLoading: costLoading,
    isError: costError,
    error: costErrorObj,
    refetch: refetchCost,
  } = useQuery({
    queryKey: ['user-cost-7d'],
    queryFn: () => getUserCostAggregate(7),
    refetchInterval: 60_000,
    retry: false,
  })
  const {
    data: openQs,
    isLoading: openQsLoading,
    isError: openQsError,
    error: openQsErrorObj,
    refetch: refetchOpenQs,
  } = useQuery({
    queryKey: ['open-questions-digest'],
    queryFn: getOpenQuestionsDigest,
    refetchInterval: 60_000,
    retry: false,
  })

  const showCostSkeleton = useDebouncedLoading(costLoading)
  const showOpenQsSkeleton = useDebouncedLoading(openQsLoading)
  const showRunsSkeleton = useDebouncedLoading(runsLoading)

  const recent = (runs ?? [])
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 10)

  function submitQuickResearch(e: FormEvent) {
    e.preventDefault()
    const q = quickQuery.trim()
    if (!q) return
    navigate(`/research?q=${encodeURIComponent(q)}`)
  }

  const topTactic     = perf?.tactics?.[0]
  const topTechnique  = perf?.techniques?.[0]
  const availablePlugins = (plugins ?? []).filter(p => p.available)
  const topPlugins    = availablePlugins.slice(0, 5)

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-6">
        <h1 className="text-lg font-semibold">Dashboard</h1>

        {/* ── Quick research ─────────────────────────────────────────────── */}
        <section
          className="rounded-lg border p-4 flex flex-col gap-2"
          style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold">Research</h2>
            <Link to="/research" className="text-[11px] text-sky-400 hover:underline">
              Open research →
            </Link>
          </div>
          <form onSubmit={submitQuickResearch} className="flex items-center gap-2">
            <input
              type="text"
              value={quickQuery}
              onChange={(e) => setQuickQuery(e.target.value)}
              placeholder="Ask anything — I'll research it for you."
              className="flex-1 px-3 py-2 rounded text-sm outline-none"
              style={{
                background: 'var(--panel2)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
              }}
            />
            <button
              type="button"
              onClick={() => setTemplatesOpen(v => !v)}
              className="px-3 py-2 rounded text-sm"
              style={{
                background: 'var(--panel2)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
              }}
              title="Use a built-in investigation template (KYC, due diligence, market mapping...)"
              data-testid="templates-toggle"
            >
              Templates {templatesOpen ? '▴' : '▾'}
            </button>
            <button
              type="submit"
              disabled={!quickQuery.trim()}
              className="px-3 py-2 rounded text-sm font-semibold disabled:opacity-50"
              style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}
            >
              Research
            </button>
          </form>
          {templatesOpen && templates && templates.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 mt-2">
              {templates.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    setQuickQuery(t.query_template)
                    setTemplatesOpen(false)
                  }}
                  className="text-left rounded p-2"
                  style={{
                    background: 'var(--panel2)',
                    border: '1px solid var(--border)',
                    color: 'var(--text)',
                  }}
                  title={t.description}
                  data-testid={`template-${t.id}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-semibold">{t.name}</span>
                    <span className="text-[9px] uppercase tracking-wider opacity-50">
                      {t.category}
                    </span>
                  </div>
                  <div className="text-[10px] mt-0.5" style={{ color: 'var(--subtext)' }}>
                    {t.description}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* ── KPI strip ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Runs Today" value={metrics?.runs_today ?? '—'} sub="since 00:00 local" />
          <StatCard
            title="Success Rate"
            value={metrics ? `${Math.round((metrics.success_rate ?? 0) * 100)}%` : '—'}
            sub="last 7 days"
          />
          <StatCard
            title="Live"
            value={metrics?.live_runs ?? '—'}
            sub={<WorkerBadge health={workerHealth} />}
          />
          <StatCard
            title="Errors"
            value={metrics?.error_count ?? '—'}
            sub="last 24 h"
            emphasis={(metrics?.error_count ?? 0) > 0 ? 'danger' : 'normal'}
          />
        </div>

        {/* ── 3 summary cards: Plugins / Wallet / Performance ─────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SummaryCard
            title="Plugins"
            link="/plugins"
            linkLabel="Browse plugins →"
            count={availablePlugins.length}
            countLabel="available"
          >
            {topPlugins.length === 0 ? (
              <p className="text-[11px] text-muted-foreground italic">No plugins available.</p>
            ) : (
              <ul className="space-y-1">
                {topPlugins.map(p => (
                  <li key={p.name} className="text-[11px] truncate flex items-center gap-1.5"
                      style={{ color: 'var(--text)' }}
                      title={p.description}>
                    <span className="inline-block w-1 h-1 rounded-full"
                          style={{ background: p.requires_api_key ? '#fbbf24' : '#4ade80' }} />
                    <span className="truncate">{p.name}</span>
                    <span className="ml-auto inline-flex items-center gap-1">
                      {p.visibility === 'private' ? (
                        <span className="text-[9px] uppercase tracking-wider px-1 py-px rounded border border-sky-700/50 text-sky-300/80">
                          private
                        </span>
                      ) : (
                        <span className="text-[9px] uppercase tracking-wider opacity-40">
                          public
                        </span>
                      )}
                      {p.requires_api_key && (
                        <span className="text-[9px] uppercase tracking-wider opacity-50">key</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </SummaryCard>

          <SummaryCard
            title="Wallet"
            link="/wallet"
            linkLabel="Manage wallet →"
            count={wallet ? wallet.available_ru.toLocaleString() : '—'}
            countLabel="RU available"
          >
            {!wallet ? (
              <p className="text-[11px] text-muted-foreground italic">Wallet not configured.</p>
            ) : (
              <dl className="space-y-1 text-[11px]" style={{ color: 'var(--text)' }}>
                <Row label="Balance"  value={wallet.balance_ru.toLocaleString()} />
                <Row label="Held"     value={wallet.held_ru.toLocaleString()}    />
                <Row label="Floor"    value={wallet.floor_ru.toLocaleString()}   />
                <Row label="Lifetime spent"
                     value={wallet.spent_ru_lifetime.toLocaleString()}
                     muted />
              </dl>
            )}
          </SummaryCard>

          <SummaryCard
            title="Performance"
            link="/performance"
            linkLabel="View dashboard →"
            count={perf?.total_runs ?? '—'}
            countLabel="runs evaluated"
          >
            {!perf || perf.total_runs === 0 ? (
              <p className="text-[11px] text-muted-foreground italic">No performance data yet.</p>
            ) : (
              <dl className="space-y-1 text-[11px]" style={{ color: 'var(--text)' }}>
                {topTactic && (
                  <Row label="Top tactic"
                       value={`${topTactic.name ?? '—'} · ${topTactic.avg_grade ?? '—'}`} />
                )}
                {topTechnique && (
                  <Row label="Top technique"
                       value={`${topTechnique.tool ?? '—'} · ${topTechnique.avg_grade ?? '—'}`} />
                )}
                <Row label="Techniques tracked"
                     value={String(perf.techniques?.length ?? 0)}
                     muted />
              </dl>
            )}
          </SummaryCard>
        </div>

        {/* ── Absorption widgets ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* G. User-level cost */}
          <div
            className="rounded-lg border p-4"
            style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}
          >
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                Spend · 7d
              </h3>
              <Link to="/wallet" className="text-[11px] text-sky-400 hover:underline">View wallet →</Link>
            </div>
            {showCostSkeleton ? (
              <>
                <Skeleton className="h-7 w-24 mt-1" />
                <div className="mt-2 space-y-1">
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-4/5" />
                  <Skeleton className="h-3 w-3/5" />
                </div>
              </>
            ) : costError ? (
              <InlineError
                title="Couldn't load spend"
                message={(costErrorObj as Error | undefined)?.message}
                onRetry={() => refetchCost()}
                inline
                className="mt-2"
              />
            ) : !costAgg || costAgg.total_ru === 0 ? (
              <EmptyState
                title="No spend this week"
                hint="Start a run to see RU usage by phase."
                compact
              />
            ) : (
              <>
                <div className="text-xl font-semibold mt-1" style={{ color: 'var(--text)' }}>
                  {costAgg.total_ru} <span className="text-[10px] uppercase opacity-50 ml-1">RU</span>
                </div>
                <div className="mt-2 text-[11px] space-y-0.5" style={{ color: 'var(--subtext)' }}>
                  {Object.entries(costAgg.by_phase).map(([phase, ru]) => (
                    <div key={phase} className="flex items-baseline justify-between">
                      <span className="opacity-70">{phase}</span>
                      <span className="tabular-nums">{ru}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* H. Open questions digest */}
          <div
            className="rounded-lg border p-4 lg:col-span-2"
            style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}
          >
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                Open Questions {openQs?.open_count ? `(${openQs.open_count})` : ''}
              </h3>
              <span className="text-[10px] opacity-50">last 30 days</span>
            </div>
            {showOpenQsSkeleton ? (
              <div className="mt-2 space-y-1.5">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-10/12" />
                <Skeleton className="h-4 w-9/12" />
              </div>
            ) : openQsError ? (
              <InlineError
                title="Couldn't load open questions"
                message={(openQsErrorObj as Error | undefined)?.message}
                onRetry={() => refetchOpenQs()}
                inline
                className="mt-2"
              />
            ) : openQs && openQs.questions.length > 0 ? (
              <ul className="mt-2 space-y-1.5 text-[11px]">
                {openQs.questions.slice(0, 5).map((q, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="opacity-40">•</span>
                    <span className="flex-1 truncate" title={q.question} style={{ color: 'var(--text)' }}>
                      {q.question}
                    </span>
                    <Link to={`/runs?open=${q.run_id}`}
                          className="text-sky-400 hover:underline text-[10px] flex-shrink-0">
                      open
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                title="No open questions"
                hint="Unresolved questions from your runs in the last 30 days will appear here."
                compact
              />
            )}
          </div>
        </div>

        {/* ── History (10 recent runs) ───────────────────────────────────── */}
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold opacity-70">History · 10 most recent</h2>
            <Link to="/runs" className="text-[11px] text-sky-400 hover:underline">
              View all →
            </Link>
          </div>
          {showRunsSkeleton ? (
            <div className="space-y-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : runsError ? (
            <InlineError
              title="Couldn't load recent runs"
              message={(runsErrorObj as Error | undefined)?.message}
              onRetry={() => refetchRuns()}
            />
          ) : recent.length === 0 ? (
            <EmptyState
              title="No runs yet"
              hint="Start your first investigation from the Research box above."
            />
          ) : (
            <RunListTable
              rows={recent}
              onShow={openDrawer}
              onRerun={(query) => navigate(`/research?q=${encodeURIComponent(query)}`)}
            />
          )}
        </section>
      </div>
      <IconRail />
    </div>
  )
}

// ─── Small primitives ──────────────────────────────────────────────────────

function WorkerBadge({ health }: { health: WorkerHealth | undefined }) {
  if (!health) {
    return <span className="text-[10px]" style={{ color: 'var(--muted)' }}>checking…</span>
  }
  const isDown      = health.temporal !== 'ok'
  const oldestQueue = health.oldest_queued_age_seconds ?? 0
  const isSlow      = !isDown && oldestQueue > 60
  const color = isDown ? '#ef4444' : isSlow ? '#fbbf24' : '#4ade80'
  const label = isDown
    ? 'worker down'
    : isSlow
      ? `worker slow (oldest queued ${Math.round(oldestQueue / 60)}m)`
      : 'worker ok'
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px]"
          style={{ color: 'var(--muted)' }}
          title={`queued=${health.queued_count} · running=${health.running_count} · temporal=${health.temporal}`}>
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  )
}

function SummaryCard({
  title, link, linkLabel, count, countLabel, children,
}: {
  title: string
  link: string
  linkLabel: string
  count: string | number
  countLabel: string
  children: React.ReactNode
}) {
  return (
    <div
      className="rounded-lg border p-4 flex flex-col gap-2"
      style={{ background: 'var(--panel)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{title}</h3>
        <Link to={link} className="text-[11px] text-sky-400 hover:underline">
          {linkLabel}
        </Link>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-xl font-semibold" style={{ color: 'var(--text)' }}>{count}</span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{countLabel}</span>
      </div>
      <div className="pt-1">{children}</div>
    </div>
  )
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`tabular-nums ${muted ? 'text-muted-foreground' : ''}`}>{value}</dd>
    </div>
  )
}
