import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatusBadge } from './StatusBadge'
import { DownloadMenu } from './DownloadMenu'
import { RotateCcw } from 'lucide-react'
import type { RunRow } from '@/api/v3'

interface Props {
  rows: RunRow[]
  onShow: (runId: string) => void
  onRerun?: (query: string) => void
}

const COMPLETED = new Set(['succeeded', 'failed', 'cancelled'])

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

export function RunListTable({ rows, onShow, onRerun }: Props) {
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
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell className="max-w-[320px] truncate text-foreground" title={row.query || undefined}>
              {row.query || <span className="opacity-40 italic">—</span>}
            </TableCell>
            <TableCell>
              <Badge variant="outline">{row.pipeline_name ? 'pipeline' : 'IS'}</Badge>
            </TableCell>
            <TableCell><StatusBadge status={row.status} /></TableCell>
            <TableCell title={row.created_at}>{relativeTime(row.created_at)}</TableCell>
            <TableCell>{durationLabel(row)}</TableCell>
            <TableCell className="text-right space-x-2">
              {row.status === 'failed' && onRerun && row.query && (
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
              <Button variant="outline" size="sm" onClick={() => onShow(row.id)}>Show</Button>
              {COMPLETED.has(row.status) && <DownloadMenu runId={row.id} />}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
