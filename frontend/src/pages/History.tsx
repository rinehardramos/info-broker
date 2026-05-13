import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import IconRail from '@/components/layout/IconRail'
import { RunListTable } from '@/components/runs/RunListTable'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { listRuns, type RunRow } from '@/api/v3'

const PAGE_SIZE = 50

export default function History() {
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

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">From</span>
            <input
              aria-label="from"
              type="date"
              value={from}
              onChange={(e) => { setFrom(e.target.value); setPage(0) }}
              className="rounded border px-2 py-1 text-sm bg-transparent"
            />
          </label>
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">To</span>
            <input
              aria-label="to"
              type="date"
              value={to}
              onChange={(e) => { setTo(e.target.value); setPage(0) }}
              className="rounded border px-2 py-1 text-sm bg-transparent"
            />
          </label>
          <label className="flex flex-col text-xs gap-1">
            <span className="opacity-70">Status</span>
            <select
              aria-label="status"
              value={status}
              onChange={(e) => { setStatus(e.target.value); setPage(0) }}
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

        <RunListTable rows={pageRows} onShow={openDrawer} />

        {filtered.length > PAGE_SIZE && (
          <div className="flex items-center gap-2 text-sm">
            <button
              className="rounded border px-2 py-1 disabled:opacity-40"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >Prev</button>
            <span>Page {page + 1} / {totalPages}</span>
            <button
              className="rounded border px-2 py-1 disabled:opacity-40"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >Next</button>
          </div>
        )}
      </div>
      <IconRail />
    </div>
  )
}
