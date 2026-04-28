import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listJobs, type JobOut } from '../../api/v3'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import JobItem from './JobItem'

export default function LiveStream() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 30_000 })
  const [liveEvents, setLiveEvents] = useState<JobOut[]>([])

  useWebSocket((event: WsEvent) => {
    if (['job.update', 'job.completed', 'job.failed'].includes(event.type) && event.job_id) {
      setLiveEvents(prev => {
        const exists = prev.find(j => j.id === event.job_id)
        const updated: JobOut = exists
          ? { ...exists, status: event.status ?? exists.status, result_count: event.result_count ?? exists.result_count }
          : {
              id: event.job_id!,
              status: event.status ?? 'running',
              query: event.message ?? '…',
              created_at: new Date().toISOString(),
              completed_at: null,
              result_count: event.result_count ?? 0,
            }
        return exists ? prev.map(j => j.id === event.job_id ? updated : j) : [updated, ...prev]
      })
      if (event.type === 'job.completed') {
        qc.invalidateQueries({ queryKey: ['jobs'] })
      }
    }
  })

  const merged: JobOut[] = [
    ...liveEvents,
    ...jobs.filter(j => !liveEvents.find(l => l.id === j.id)),
  ].slice(0, 50)

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-[11px] font-semibold" style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}>
        Live
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {merged.length === 0 && (
          <p className="text-[10px] text-center mt-6" style={{ color: 'var(--muted)' }}>
            No active jobs
          </p>
        )}
        {merged.map(job => <JobItem key={job.id} job={job} />)}
      </div>
    </div>
  )
}
