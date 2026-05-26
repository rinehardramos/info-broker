import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import { useSessionStore } from '../stores/sessionStore'
import {
  listBenchmarkReports,
  getBenchmarkReport,
  runBenchmark,
  getBenchmarkRunStatus,
} from '../api/v3'

const num = (v: unknown, d = 2): string =>
  typeof v === 'number' ? v.toFixed(d) : '—'

function grade(mean: number | null | undefined): { letter: string; color: string } {
  if (mean == null) return { letter: '—', color: 'var(--muted)' }
  if (mean >= 0.85) return { letter: 'A', color: '#34d399' }
  if (mean >= 0.70) return { letter: 'B', color: '#34d399' }
  if (mean >= 0.55) return { letter: 'C', color: '#fbbf24' }
  if (mean >= 0.40) return { letter: 'D', color: '#fb923c' }
  return { letter: 'F', color: '#f87171' }
}

const SEV_COLOR: Record<string, string> = {
  critical: '#f87171', error: '#f87171', warning: '#fbbf24', info: '#60a5fa',
}

export default function BenchmarkReportsPage() {
  const isAdmin = useSessionStore(s => s.isAdmin)
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const reportsQ = useQuery({ queryKey: ['benchmarkReports'], queryFn: listBenchmarkReports, enabled: isAdmin })
  const statusQ = useQuery({
    queryKey: ['benchmarkRunStatus'], queryFn: getBenchmarkRunStatus, enabled: isAdmin,
    refetchInterval: 15000,
  })
  const reportQ = useQuery({
    queryKey: ['benchmarkReport', selectedId], queryFn: () => getBenchmarkReport(selectedId!),
    enabled: isAdmin && !!selectedId,
  })

  // auto-select the newest report; refresh the list when a run finishes
  useEffect(() => {
    const list = reportsQ.data
    if (list && list.length && !selectedId) setSelectedId(list[0].id)
  }, [reportsQ.data, selectedId])

  const wasActive = statusQ.data?.active
  useEffect(() => {
    if (wasActive === false) { qc.invalidateQueries({ queryKey: ['benchmarkReports'] }) }
  }, [wasActive, qc])

  const runMut = useMutation({
    mutationFn: () => runBenchmark(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['benchmarkRunStatus'] }) },
  })

  if (!isAdmin) {
    return (
      <div style={{ display: 'flex' }}>
        <div style={{ flex: 1, padding: 24, color: 'var(--text)' }}>Admin only.</div>
        <IconRail />
      </div>
    )
  }

  const active = statusQ.data?.active
  const report = (reportQ.data?.report ?? {}) as any
  const items: any[] = report.item_results ?? []
  const meta: any[] = report.run_metadata ?? []
  const overall = report.aggregates?.overall ?? {}
  const cost = report.aggregates?.cost_summary ?? {}
  const recs: any[] = report.recommendations ?? []
  const g = grade(overall.mean_score)
  const metaById = (id: string) => meta.find(m => m.run_id && items.find(it => it.item_id === id))

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <div style={{ flex: 1, padding: '24px 28px', color: 'var(--text)', maxWidth: 1100, overflow: 'auto' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>Benchmark Reports</h1>
          <button
            data-testid="bench-run"
            onClick={() => runMut.mutate()}
            disabled={active || runMut.isPending}
            style={{
              fontSize: 12, padding: '6px 14px', borderRadius: 6, border: 'none',
              background: active ? 'var(--panel2)' : 'var(--accent)',
              color: active ? 'var(--muted)' : '#fff',
              cursor: active || runMut.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {active ? 'Run in progress…' : runMut.isPending ? 'Starting…' : 'Run benchmark'}
          </button>
        </div>

        {active && (
          <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 6, fontSize: 12,
            background: 'rgba(251,191,36,0.12)', color: '#fbbf24' }}>
            A benchmark run is in progress (started {statusQ.data?.started_at?.slice(0, 16).replace('T', ' ')} UTC).
            Real brain time — several minutes per item. The new report appears here when it finishes.
          </div>
        )}

        {!reportsQ.data?.length ? (
          <p style={{ color: 'var(--subtext)', fontSize: 13 }}>
            No benchmark reports yet. Click <strong>Run benchmark</strong> (or run
            <code> python -m benchmarks.run_benchmark</code> with <code>BENCHMARK_INGEST_URL</code> set) to create one.
          </p>
        ) : (
          <>
            {/* Report selector */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: 'var(--muted)', marginRight: 8 }}>Report:</label>
              <select
                data-testid="bench-report-select"
                value={selectedId ?? ''}
                onChange={e => setSelectedId(e.target.value)}
                style={{ fontSize: 12, padding: '4px 8px', borderRadius: 4, background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
              >
                {reportsQ.data.map(r => (
                  <option key={r.id} value={r.id}>
                    {r.created_at.slice(0, 16).replace('T', ' ')} — {r.label ?? 'run'} ({num(r.mean_score)})
                  </option>
                ))}
              </select>
            </div>

            {/* Headline rating */}
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20, flexWrap: 'wrap' }}>
              <div style={{ padding: '14px 22px', borderRadius: 10, background: 'var(--panel)', border: '1px solid var(--border)', textAlign: 'center' }}>
                <div style={{ fontSize: 40, fontWeight: 800, color: g.color, lineHeight: 1 }} data-testid="bench-mean-score">
                  {overall.mean_score != null ? `${(overall.mean_score * 100).toFixed(1)}%` : '—'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>mean score · grade {g.letter}</div>
              </div>
              <Stat label="items" value={overall.total_items ?? items.length} />
              <Stat label="gamed" value={`${num(overall.gamed_pct, 0)}%`}
                color={overall.gamed_items ? '#f87171' : '#34d399'} />
              <Stat label="RU cost" value={cost.total_ru_consumed ?? '—'} />
              <Stat label="cost/lead" value={num(cost.cost_per_lead)} />
              <Stat label="avg duration" value={cost.avg_duration_s ? `${Math.round(cost.avg_duration_s)}s` : '—'} />
            </div>

            {/* Per-item table */}
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginBottom: 24 }}>
              <thead>
                <tr style={{ color: 'var(--muted)', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '6px 8px' }}>Item</th>
                  <th style={{ padding: '6px 8px' }}>Score</th>
                  <th style={{ padding: '6px 8px' }}>Coverage</th>
                  <th style={{ padding: '6px 8px' }}>Source qual.</th>
                  <th style={{ padding: '6px 8px' }}>Leads</th>
                  <th style={{ padding: '6px 8px' }}>Field cov.</th>
                  <th style={{ padding: '6px 8px' }}>Guard</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const rich = it.richness ?? {}
                  return (
                    <tr key={it.item_id ?? i} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '6px 8px' }}>{it.item_id}</td>
                      <td style={{ padding: '6px 8px', fontWeight: 600 }}>{num(it.item_score)}</td>
                      <td style={{ padding: '6px 8px' }}>{num(it.coverage)}</td>
                      <td style={{ padding: '6px 8px' }}>{num(it.source_quality)}</td>
                      <td style={{ padding: '6px 8px' }}>{rich.lead_count ?? '—'}</td>
                      <td style={{ padding: '6px 8px' }}>{num(rich.field_coverage)}</td>
                      <td style={{ padding: '6px 8px', color: it.tripped_guard ? '#f87171' : 'var(--muted)' }}>
                        {it.tripped_guard ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {/* Recommendations */}
            {recs.length > 0 && (
              <section style={{ marginBottom: 24 }}>
                <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Recommendations</h2>
                {recs.map((r, i) => (
                  <div key={i} style={{ fontSize: 12, padding: '6px 10px', marginBottom: 6, borderRadius: 4,
                    background: 'var(--panel)', borderLeft: `3px solid ${SEV_COLOR[r.severity] ?? 'var(--border)'}` }}>
                    <span style={{ color: SEV_COLOR[r.severity] ?? 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', fontSize: 10 }}>
                      {r.severity} · {r.category}
                    </span>
                    <div style={{ color: 'var(--text)', marginTop: 2 }}>{r.message ?? r.detail}</div>
                  </div>
                ))}
              </section>
            )}

            {/* Analysis / methodology */}
            <section style={{ fontSize: 12, color: 'var(--subtext)', lineHeight: 1.7,
              background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 16px' }}>
              <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>How to read this</h2>
              <p><strong>item_score = coverage × source_quality.</strong> Coverage = fraction of the item&apos;s
                curated authoritative facts matched. Source quality weights provenance
                (primary_official / live_official = 1.0, live_search = 0.75, training = 0).
                Four anti-gaming guards hard-zero any run that fabricates from training data, uses
                unregistered tools, skips phases, or RAG-shortcuts — so a clean run with 0% gamed is
                doing real live research.</p>
              <p style={{ marginTop: 6 }}><strong>field_coverage</strong> = fraction of the 10 lead fields
                (address/price/listing_url/agent &amp; owner name/email/phone/background) surfaced run-wide —
                it reflects enrichment breadth even when fields land in separate, not-yet-merged leads.</p>
              <p style={{ marginTop: 6 }}><strong>Known ceilings &amp; caveats:</strong> free enrichment works
                where data is page-available (agent contact); FSBO-platform <em>seller</em> contact is gated
                behind logins/forms (a data wall, not a tooling gap); county open-data APIs are the robust
                free owner source. Runs are <em>stochastic</em> — a single item can swing (e.g. a thin 2-tool-call
                run), so trust the trend across multiple reports, not one number. Scores shown are the
                <strong> no-key</strong> free-capability baseline unless a run had keys configured.</p>
            </section>
          </>
        )}
      </div>
      <IconRail />
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div style={{ padding: '10px 16px', borderRadius: 8, background: 'var(--panel)', border: '1px solid var(--border)', textAlign: 'center', minWidth: 78 }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: color ?? 'var(--text)' }}>{value}</div>
      <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{label}</div>
    </div>
  )
}
