/**
 * RunSubprocessTimeline — flat vertical list of streamed nodes for a single
 * run, rendered as subprocess rows under a PipelineRunItem.
 *
 * Distinct from FlowMiniPreview (which is a graph diagram in the Results
 * pane); this is just a chronological readout of what the run executed,
 * suitable for an inline expand under each run row in the Live rail.
 */
import { useRunStreamStore } from '@/stores/runStreamStore'
import type { NodeCardStatus } from '@/stores/runStreamStore'

const STATUS_COLOR: Record<NodeCardStatus, string> = {
  pending:   'var(--muted)',
  running:   '#fbbf24',
  streaming: '#fbbf24',
  succeeded: '#4ade80',
  failed:    '#ef4444',
  canceled:  'var(--muted)',
}

function elapsedMs(startedAt?: number, finishedAt?: number): string {
  if (!startedAt) return ''
  const end = finishedAt ?? Date.now()
  const ms = end - startedAt
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m${Math.floor((ms % 60_000) / 1000)}s`
}

interface Props {
  runId: string
}

export default function RunSubprocessTimeline({ runId }: Props) {
  const run = useRunStreamStore((s) => s.runsById[runId])
  if (!run) {
    return (
      <div className="pl-4 pr-2 py-1.5 text-[10px] italic" style={{ color: 'var(--muted)' }}>
        No streamed nodes yet.
      </div>
    )
  }
  if (run.cardOrder.length === 0) {
    return (
      <div className="pl-4 pr-2 py-1.5 text-[10px] italic" style={{ color: 'var(--muted)' }}>
        Waiting for first node…
      </div>
    )
  }
  return (
    <div className="pl-3 pr-2 pb-2 flex flex-col gap-0.5">
      {run.cardOrder.map((nodeId) => {
        const c = run.cards[nodeId]
        if (!c) return null
        const dot = STATUS_COLOR[c.status] ?? 'var(--muted)'
        const elapsed = elapsedMs(c.startedAt, c.finishedAt)
        return (
          <div
            key={nodeId}
            className="flex items-center gap-1.5 text-[10px] pl-2"
            style={{ color: 'var(--subtext)', borderLeft: '1px solid var(--border)' }}
            title={c.pluginOrTool ?? c.nodeName}
          >
            <span style={{ color: dot, fontSize: 7 }}>●</span>
            <span className="truncate flex-1" style={{ color: 'var(--text)' }}>
              {c.nodeName || c.nodeId}
            </span>
            {elapsed && (
              <span style={{ color: 'var(--muted)', fontSize: 9 }}>{elapsed}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
