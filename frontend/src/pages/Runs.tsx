/**
 * Runs page — augmented run history with cost (RU) column.
 *
 * Preserves History.tsx URL (/history) behaviour by co-existing alongside it.
 * This page lives at /runs and adds a "Cost (RU)" column plus a slide-in
 * cost breakdown panel per run. Existing /history bookmarks are not broken.
 *
 * Cost data is lazy-loaded per run on click via useRunCostBreakdown to avoid
 * N+1 requests on the list.
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import IconRail from '@/components/layout/IconRail'
import { StatusBadge } from '@/components/runs/StatusBadge'
import { DownloadMenu } from '@/components/runs/DownloadMenu'
import { RunCostBreakdown } from '@/components/wallet/RunCostBreakdown'
import { listRuns, type RunRow } from '@/api/v3'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { X } from 'lucide-react'

const COMPLETED = new Set(['succeeded', 'failed', 'canceled'])

const PAGE_SIZE = 50

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function durationLabel(row: RunRow): string {
  if (!row.finished_at) return '—'
  const sec = Math.round(
    (new Date(row.finished_at).getTime() - new Date(row.created_at).getTime()) / 1000,
  )
  return `${sec}s`
}

export default function Runs() {
  const navigate = useNavigate()
  const openDrawer = useResultDrawerStore((s) => s.open)
  const { data: runs } = useQuery({
    queryKey: ['all-runs'],
    queryFn: listRuns,
    refetchInterval: 30_000,
  })

  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  const filtered = useMemo<RunRow[]>(() => {
    const list = (runs ?? []).slice().sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    return list.filter((r) => {
      if (status && r.status !== status) return false
      if (from && new Date(r.created_at) < new Date(from)) return false
      if (to && new Date(r.created_at) > new Date(`${to}T23:59:59`)) return false
      return true
    })
  }, [runs, status, from, to])

  const pageStart = page * PAGE_SIZE
  const pageRows = filtered.slice(pageStart, pageStart + PAGE_SIZE)
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-4">
        <h1 className="text-lg font-semibold">History</h1>

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">From</span>
            <input
              aria-label="from"
              type="date"
              value={from}
              onChange={e => { setFrom(e.target.value); setPage(0) }}
              className="rounded border px-2 py-1 text-sm bg-transparent"
            />
          </label>
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">To</span>
            <input
              aria-label="to"
              type="date"
              value={to}
              onChange={e => { setTo(e.target.value); setPage(0) }}
              className="rounded border px-2 py-1 text-sm bg-transparent"
            />
          </label>
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">Status</span>
            <select
              aria-label="status"
              value={status}
              onChange={e => { setStatus(e.target.value); setPage(0) }}
              className="rounded border px-2 py-1 text-sm bg-transparent"
            >
              <option value="">All</option>
              <option value="queued">queued</option>
              <option value="running">running</option>
              <option value="succeeded">succeeded</option>
              <option value="failed">failed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
        </div>

        {/* Table */}
        {pageRows.length === 0 ? (
          <div className="rounded border p-8 text-center text-sm opacity-70">
            No runs yet — start one from Research.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Query', 'Type', 'Status', 'Started', 'Duration', 'Cost (RU)', ''].map(h => (
                    <th
                      key={h}
                      style={{
                        padding: '6px 10px',
                        textAlign: 'left',
                        fontSize: 11,
                        color: 'var(--muted)',
                        fontWeight: 500,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map(row => {
                  const isSelected = selectedRunId === row.id
                  return (
                    <tr
                      key={row.id}
                      style={{
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                        background: isSelected ? 'rgba(167,139,250,0.07)' : undefined,
                        transition: 'background 0.1s',
                      }}
                    >
                      <td
                        style={{
                          padding: '8px 10px',
                          maxWidth: 300,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          color: 'var(--text)',
                        }}
                        title={row.query ?? undefined}
                      >
                        {row.query || <span style={{ opacity: 0.4, fontStyle: 'italic' }}>—</span>}
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--muted)', fontSize: 11 }}>
                        {row.pipeline_name ? 'pipeline' : 'IS'}
                      </td>
                      <td style={{ padding: '8px 10px' }}>
                        <StatusBadge status={row.status} />
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--muted)', fontSize: 11 }}>
                        {relativeTime(row.created_at)}
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--muted)', fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
                        {durationLabel(row)}
                      </td>
                      <td style={{ padding: '8px 10px', display: 'flex', gap: 6 }}>
                        <button
                          onClick={() => openDrawer(row.id)}
                          style={{
                            padding: '3px 8px',
                            borderRadius: 4,
                            border: '1px solid var(--border)',
                            background: 'transparent',
                            color: 'var(--text)',
                            fontSize: 11,
                            cursor: 'pointer',
                          }}
                          title="Open this run's details (turns, synthesis, ACH ranking, findings)"
                        >
                          Show
                        </button>
                        <button
                          onClick={() => navigate(`/research?replay=${row.id}`)}
                          style={{
                            padding: '3px 8px',
                            borderRadius: 4,
                            border: '1px solid #a78bfa',
                            background: 'transparent',
                            color: '#a78bfa',
                            fontSize: 11,
                            cursor: 'pointer',
                          }}
                          title="Open this run in the research view"
                        >
                          View
                        </button>
                        {COMPLETED.has(row.status) && <DownloadMenu runId={row.id} />}
                        <button
                          onClick={() => setSelectedRunId(isSelected ? null : row.id)}
                          style={{
                            padding: '3px 8px',
                            borderRadius: 4,
                            border: '1px solid var(--border)',
                            background: 'transparent',
                            color: isSelected ? '#a78bfa' : 'var(--muted)',
                            fontSize: 11,
                            cursor: 'pointer',
                          }}
                          title="View cost breakdown"
                        >
                          Cost
                        </button>
                      </td>
                      <td style={{ padding: '8px 10px' }} />
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {filtered.length > PAGE_SIZE && (
          <div className="flex items-center gap-2 text-sm">
            <button
              className="rounded border px-2 py-1 disabled:opacity-40"
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
            >
              Prev
            </button>
            <span>Page {page + 1} / {totalPages}</span>
            <button
              className="rounded border px-2 py-1 disabled:opacity-40"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Cost breakdown side panel */}
      {selectedRunId && (
        <div
          style={{
            width: 320,
            flexShrink: 0,
            background: 'var(--panel)',
            borderLeft: '1px solid var(--border)',
            overflow: 'auto',
            padding: 20,
            position: 'relative',
          }}
        >
          <button
            onClick={() => setSelectedRunId(null)}
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--muted)',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Close"
          >
            <X size={14} />
          </button>
          <RunCostBreakdown runId={selectedRunId} />
        </div>
      )}

      <IconRail />
    </div>
  )
}
