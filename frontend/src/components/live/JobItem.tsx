import { useSessionStore } from '../../stores/sessionStore'
import type { JobOut } from '../../api/v3'

const statusStyle: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  completed: '#4ade80',
  failed:    '#ef4444',
  cancelled: 'var(--muted)',
}

interface Props {
  job: JobOut & { live?: boolean }
}

export default function JobItem({ job }: Props) {
  const setCol1Content = useSessionStore(s => s.setCol1Content)

  return (
    <div
      onClick={() => setCol1Content({ type: 'job', jobId: job.id })}
      className="px-3 py-2 mb-1 rounded cursor-pointer text-xs transition-colors"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-1 mb-1">
        <span style={{ color: statusStyle[job.status] ?? 'var(--muted)', fontSize: 8 }}>●</span>
        <span style={{ color: 'var(--subtext)', fontSize: 10 }}>{job.status}</span>
        {job.result_count > 0 && (
          <span className="ml-auto" style={{ color: 'var(--accent)', fontSize: 10 }}>
            {job.result_count} results
          </span>
        )}
      </div>
      <div className="truncate" style={{ color: 'var(--text)' }}>{job.query}</div>
    </div>
  )
}
