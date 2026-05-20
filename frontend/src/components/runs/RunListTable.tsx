import { useState } from 'react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatusBadge } from './StatusBadge'
import { DownloadMenu } from './DownloadMenu'
import { RotateCcw } from 'lucide-react'
import { cancelPipelineRun } from '@/api/v3'
import type { RunRow } from '@/api/v3'

interface Props {
  rows: RunRow[]
  onShow: (runId: string) => void
  onRerun?: (query: string) => void
}

const COMPLETED = new Set(['succeeded', 'failed', 'cancelled'])
const STUCK_AFTER_MS = 5 * 60_000

function durationLabel(row: RunRow): string {
  if (!row.finished_at) return '—'
  const sec = Math.round(
    (new Date(row.finished_at).getTime() - new Date(row.created_at).getTime()) / 1000,
  )
  return `${sec}s`
}

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function isStuck(row: RunRow): boolean {
  if (row.status !== 'queued' && row.status !== 'running') return false
  const ageMs = Date.now() - new Date(row.created_at).getTime()
  return ageMs > STUCK_AFTER_MS
}

export function RunListTable({ rows, onShow, onRerun }: Props) {
  const [cancelling, setCancelling] = useState<Set<string>>(new Set())

  async function handleCancel(runId: string) {
    setCancelling(prev => new Set(prev).add(runId))
    try { await cancelPipelineRun(runId) }
    catch { /* surfaced via the row turning stale anyway */ }
    finally {
      setCancelling(prev => { const next = new Set(prev); next.delete(runId); return next })
    }
  }

  if (rows.length === 0) {
    return (
      <div className="rounded border p-8 text-center text-sm opacity-70">
        No runs yet — start one from Research.
      </div>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Query</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const stuck = isStuck(row)
          return (
          <TableRow key={row.id}>
            <TableCell className="max-w-[320px] truncate text-foreground" title={row.query || undefined}>
              {row.query || <span className="opacity-40 italic">—</span>}
            </TableCell>
            <TableCell>
              <Badge variant="outline">{row.pipeline_name ? 'pipeline' : 'IS'}</Badge>
            </TableCell>
            <TableCell>
              <span className="inline-flex items-center gap-1.5">
                <StatusBadge status={row.status} />
                {stuck && (
                  <span
                    className="text-[10px] px-1 py-px rounded border border-amber-700/60 text-amber-300 bg-amber-950/30"
                    title="Stuck > 5 min — will auto-fail at 15 min"
                  >
                    ⚠ stuck
                  </span>
                )}
              </span>
            </TableCell>
            <TableCell title={row.created_at}>{relativeTime(row.created_at)}</TableCell>
            <TableCell>{durationLabel(row)}</TableCell>
            <TableCell className="text-right">
              {/* Fixed-width slots keep the Show / Download buttons in the
                  same column across rows; empty slots collapse to spacing. */}
              <div className="inline-flex gap-2 justify-end items-center">
                <div className="w-[80px] flex justify-end">
                  {stuck ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCancel(row.id)}
                      disabled={cancelling.has(row.id)}
                      title="Cancel this stuck run"
                    >
                      {cancelling.has(row.id) ? '…' : 'Cancel'}
                    </Button>
                  ) : row.status === 'failed' && onRerun && row.query && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onRerun(row.query)}
                      title="Rerun this query"
                    >
                      <RotateCcw size={12} className="mr-1" />
                      Rerun
                    </Button>
                  )}
                </div>
                <div className="w-[60px] flex justify-end">
                  <Button variant="outline" size="sm" onClick={() => onShow(row.id)}>Show</Button>
                </div>
                <div className="w-[112px] flex justify-end">
                  {COMPLETED.has(row.status) && <DownloadMenu runId={row.id} />}
                </div>
              </div>
            </TableCell>
          </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
