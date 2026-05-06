import { useSessionStore } from '../../stores/sessionStore'
import type { PipelineRunSummary } from '../../api/pipelines'

const STATUS_COLOR: Record<string, string> = {
  queued:    'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
}

interface Props {
  run: PipelineRunSummary
}

export default function PipelineRunItem({ run }: Props) {
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const isClickable = run.status !== 'queued'

  const handleClick = () => {
    if (isClickable) {
      setCol1Content({ type: 'pipeline_run', runId: run.id })
    }
  }

  const isIS = run.trigger_type === 'agent_is'
  const progress = isIS
    ? (run.status === 'running' ? 'researching…' : 'IS research')
    : run.step_count > 0
      ? `${run.steps_done}/${run.step_count} steps`
      : 'no steps'

  return (
    <div
      onClick={handleClick}
      className="px-3 py-2 mb-1 rounded text-xs transition-colors"
      style={{
        background: 'var(--panel2)',
        border: '1px solid var(--border)',
        cursor: isClickable ? 'pointer' : 'default',
        opacity: run.status === 'queued' ? 0.6 : 1,
      }}
    >
      <div className="flex items-center gap-1 mb-1">
        <span style={{ color: STATUS_COLOR[run.status] ?? 'var(--muted)', fontSize: 8 }}>◆</span>
        <span style={{ color: 'var(--subtext)', fontSize: 10 }}>{run.status}</span>
        <span className="ml-auto" style={{ color: 'var(--muted)', fontSize: 9 }}>{progress}</span>
      </div>
      <div className="truncate" style={{ color: 'var(--text)' }}>
        {run.pipeline_name}
      </div>
    </div>
  )
}
