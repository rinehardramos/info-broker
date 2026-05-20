import { useState } from 'react'
import { useSessionStore } from '../../stores/sessionStore'
import type { PipelineRunSummary } from '../../api/pipelines'
import RunSubprocessTimeline from './RunSubprocessTimeline'

const STATUS_COLOR: Record<string, string> = {
  queued:    'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
  ask_user:  '#fbbf24',
}

interface Props {
  run: PipelineRunSummary
}

export default function PipelineRunItem({ run }: Props) {
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const isClickable = run.status !== 'queued'
  // Expand by default for in-flight runs so the user sees the subprocesses
  // streaming in without needing an extra click.
  const [expanded, setExpanded] = useState(run.status === 'running')

  const handleOpen = () => {
    if (isClickable) {
      setCol1Content({ type: 'pipeline_run', runId: run.id })
    }
  }

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded((v) => !v)
  }

  const isIS = run.trigger_type === 'agent_is'
  const progress = isIS
    ? (run.status === 'running' ? 'researching…' : 'IS research')
    : run.step_count > 0
      ? `${run.steps_done}/${run.step_count} steps`
      : 'no steps'

  return (
    <div
      className="mb-1 rounded text-xs transition-colors"
      style={{
        background: 'var(--panel2)',
        border: '1px solid var(--border)',
        opacity: run.status === 'queued' ? 0.6 : 1,
      }}
    >
      <div
        onClick={handleOpen}
        className="px-3 py-2"
        style={{ cursor: isClickable ? 'pointer' : 'default' }}
      >
        <div className="flex items-center gap-1 mb-1">
          <button
            type="button"
            onClick={handleToggle}
            aria-label={expanded ? 'Collapse subprocesses' : 'Expand subprocesses'}
            className="inline-flex items-center justify-center"
            style={{
              width: 12, height: 12, padding: 0, marginRight: 2,
              background: 'transparent', border: 'none',
              color: 'var(--muted)', cursor: 'pointer', fontSize: 9,
            }}
          >
            {expanded ? '▾' : '▸'}
          </button>
          <span style={{ color: STATUS_COLOR[run.status] ?? 'var(--muted)', fontSize: 8 }}>◆</span>
          <span style={{ color: 'var(--subtext)', fontSize: 10 }}>{run.status}</span>
          <span className="ml-auto" style={{ color: 'var(--muted)', fontSize: 9 }}>{progress}</span>
        </div>
        <div className="truncate" style={{ color: 'var(--text)' }}>
          {run.pipeline_name}
        </div>
      </div>
      {expanded && <RunSubprocessTimeline runId={run.id} />}
    </div>
  )
}
