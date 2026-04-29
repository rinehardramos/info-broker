import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listJobs, getCoreSettings, type JobOut } from '../../api/v3'
import { listAllPipelineRuns, type PipelineRunSummary } from '../../api/pipelines'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import JobItem from './JobItem'
import PipelineRunItem from './PipelineRunItem'

export default function LiveStream() {
  const qc = useQueryClient()
  const { data: coreSettings } = useQuery({
    queryKey: ['core-settings'],
    queryFn: getCoreSettings,
    staleTime: 60_000,
  })
  const retentionMs = Number(coreSettings?.settings['live_panel.retention_seconds'] ?? 600) * 1000

  const { data: jobs = [] } = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 30_000 })
  const { data: pipelineRuns = [] } = useQuery({
    queryKey: ['pipeline-runs-all'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 10_000,
  })
  const [liveEvents, setLiveEvents] = useState<JobOut[]>([])
  const [livePipelineEvents, setLivePipelineEvents] = useState<(Partial<PipelineRunSummary> & { id: string })[]>([])

  useWebSocket((event: WsEvent) => {
    // Job events
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

    // Pipeline events
    if (event.type === 'pipeline.step.update' && event.run_id) {
      setLivePipelineEvents(prev => {
        const exists = prev.find(r => r.id === event.run_id)
        if (exists) {
          const isTerminalStep = event.status === 'succeeded' || event.status === 'failed'
          return prev.map(r =>
            r.id === event.run_id
              ? { ...r, status: 'running', steps_done: isTerminalStep ? (r.steps_done ?? 0) + 1 : r.steps_done }
              : r,
          )
        }
        return [{ id: event.run_id!, status: 'running', steps_done: 0, step_count: 0 }, ...prev]
      })
    }

    if (event.type === 'pipeline.run.complete' && event.run_id) {
      setLivePipelineEvents(prev =>
        prev.map(r =>
          r.id === event.run_id
            ? { ...r, status: event.status ?? 'succeeded' }
            : r,
        ),
      )
      qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] })
    }
  })

  const cutoff = Date.now() - retentionMs

  const mergedJobs: JobOut[] = [
    ...liveEvents,
    ...jobs.filter(j => !liveEvents.find(l => l.id === j.id)),
  ].slice(0, 30)

  const mergedPipelineRuns: PipelineRunSummary[] = pipelineRuns
    .map(r => {
      const live = livePipelineEvents.find(l => l.id === r.id)
      return live ? { ...r, ...live } as PipelineRunSummary : r
    })
    .slice(0, 20)

  const visibleJobs = mergedJobs.filter(j => new Date(j.created_at).getTime() > cutoff)
  const visibleRuns = mergedPipelineRuns.filter(r => new Date(r.started_at).getTime() > cutoff)

  return (
    <div className="flex flex-col h-full">
      <div
        className="px-3 py-2 text-[11px] font-semibold"
        style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
      >
        Live
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {/* Research jobs */}
        {visibleJobs.length > 0 && (
          <>
            <div
              className="px-1 pb-1 text-[9px] font-semibold tracking-widest"
              style={{ color: 'var(--muted)' }}
            >
              RESEARCH
            </div>
            {visibleJobs.map(job => <JobItem key={job.id} job={job} />)}
          </>
        )}

        {/* Pipeline runs */}
        {visibleRuns.length > 0 && (
          <div className={visibleJobs.length > 0 ? 'mt-3' : ''}>
            <div
              className="px-1 pb-1 text-[9px] font-semibold tracking-widest"
              style={{ color: 'var(--muted)' }}
            >
              PIPELINES
            </div>
            {visibleRuns.map(run => <PipelineRunItem key={run.id} run={run} />)}
          </div>
        )}

        {visibleJobs.length === 0 && visibleRuns.length === 0 && (
          <p className="text-[10px] text-center mt-6" style={{ color: 'var(--muted)' }}>
            No active jobs
          </p>
        )}
      </div>
    </div>
  )
}
