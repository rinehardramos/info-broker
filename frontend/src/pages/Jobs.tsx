import IconRail from '../components/layout/IconRail'
import { useQuery } from '@tanstack/react-query'
import { listJobs, type JobOut } from '../api/v3'

export default function Jobs() {
  const { data: jobs = [], isLoading } = useQuery({ queryKey: ['jobs'], queryFn: listJobs })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 col-scroll p-4">
        <h2 className="text-sm font-bold mb-4" style={{ color: 'var(--accent)' }}>Jobs</h2>
        {isLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading…</p>}
        {jobs.map((job: JobOut) => (
          <div key={job.id} className="mb-2 p-3 rounded text-xs" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--subtext)' }}>{job.status}</span>
            <span className="ml-2" style={{ color: 'var(--text)' }}>{job.query}</span>
          </div>
        ))}
      </div>
      <IconRail />
    </div>
  )
}
