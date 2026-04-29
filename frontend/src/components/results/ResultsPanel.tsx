import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob, getJobResults, gradeResult } from '../../api/v3'
import { getPipelineRun } from '../../api/pipelines'
import NewsCard from './NewsCard'
import GradeBar from './GradeBar'

type Tab = 'Profiles' | 'News' | 'Social' | 'Summary'
const TABS: Tab[] = ['Profiles', 'News', 'Social', 'Summary']

const STEP_STATUS_COLOR: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
}

function PipelineRunResults({ runId }: { runId: string }) {
  const { data: run, isLoading } = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => getPipelineRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'queued' ? 3000 : false
    },
  })

  if (isLoading) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Loading…</p>
  }

  if (!run) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Run not found.</p>
  }

  const totalItems = run.steps.reduce((sum, s) => sum + s.item_count, 0)

  return (
    <div className="p-3">
      {/* Run header */}
      <div
        className="rounded p-3 mb-4 text-xs"
        style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            style={{
              fontSize: 8,
              color: STEP_STATUS_COLOR[run.status] ?? 'var(--muted)',
            }}
          >
            ◆
          </span>
          <span style={{ color: STEP_STATUS_COLOR[run.status] ?? 'var(--muted)', fontWeight: 600 }}>
            {run.status}
          </span>
          <span className="ml-auto" style={{ color: 'var(--muted)' }}>
            {totalItems > 0 ? `${totalItems} items collected` : ''}
          </span>
        </div>
        {run.status === 'running' && (
          <p style={{ color: 'var(--muted)', fontSize: 10, marginTop: 4 }}>
            ⟳ Pipeline in progress…
          </p>
        )}
      </div>

      {/* Steps */}
      <div className="text-[10px] font-semibold mb-2 tracking-widest" style={{ color: 'var(--muted)' }}>
        STEPS
      </div>
      <div className="flex flex-col gap-2">
        {run.steps.length === 0 && (
          <p className="text-xs" style={{ color: 'var(--muted)' }}>No steps recorded.</p>
        )}
        {run.steps.map((step, idx) => (
          <div
            key={step.id}
            className="rounded p-3 text-xs"
            style={{
              background: 'var(--panel2)',
              border: `1px solid ${step.status === 'failed' ? '#ef444433' : 'var(--border)'}`,
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span style={{ color: STEP_STATUS_COLOR[step.status] ?? 'var(--muted)', fontSize: 8 }}>●</span>
              <span style={{ color: 'var(--subtext)', fontWeight: 600 }}>Step {idx + 1}</span>
              <span style={{ color: 'var(--muted)' }}>·</span>
              <span style={{ color: STEP_STATUS_COLOR[step.status] ?? 'var(--muted)' }}>
                {step.status}
              </span>
              {step.item_count > 0 && (
                <span className="ml-auto" style={{ color: '#4ade80' }}>
                  {step.item_count} items
                </span>
              )}
            </div>
            {step.error_message && (
              <div
                className="mt-1 rounded px-2 py-1 text-[10px]"
                style={{ background: '#ef444411', color: '#f87171' }}
              >
                {step.error_message}
              </div>
            )}
            {step.started_at && step.finished_at && (
              <div className="mt-1 text-[9px]" style={{ color: 'var(--muted)' }}>
                {Math.round(
                  (new Date(step.finished_at).getTime() - new Date(step.started_at).getTime()) / 1000,
                )}s
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('News')
  const col1Content = useSessionStore(s => s.col1Content)

  const { data: job } = useQuery({
    queryKey: ['job', col1Content?.type === 'job' ? col1Content.jobId : null],
    queryFn: () => getJob((col1Content as { type: 'job'; jobId: string }).jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 3000 : false
    },
  })

  const { data: results = [] } = useQuery({
    queryKey: ['job-results', col1Content?.type === 'job' ? col1Content.jobId : null],
    queryFn: () => getJobResults((col1Content as { type: 'job'; jobId: string }).jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId && job?.status === 'completed',
  })

  // Pipeline run view — renders without tabs
  if (col1Content?.type === 'pipeline_run') {
    return (
      <div className="flex flex-col h-full">
        <div
          className="px-3 py-2 text-[11px] font-semibold"
          style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
        >
          Pipeline Run
        </div>
        <div className="flex-1 overflow-y-auto">
          <PipelineRunResults runId={col1Content.runId} />
        </div>
      </div>
    )
  }

  // Job / empty view — original tabs UI
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-3 gap-1 pt-2 pb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-2 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: activeTab === tab ? 'var(--panel2)' : 'transparent',
              color:      activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              border:     activeTab === tab ? '1px solid var(--border)' : '1px solid transparent',
              cursor: 'pointer',
            }}
          >
            {tab}
          </button>
        ))}
        {job && (
          <span className="ml-auto text-[10px] truncate max-w-[40%]" style={{ color: 'var(--subtext)' }}>
            {job.query}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {!col1Content && (
          <div className="text-center mt-16">
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              Send a message to the agent or tap a job in the live stream.
            </p>
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'News' && (
          <div>
            {job && (
              <p className="text-[10px] mb-3" style={{ color: 'var(--subtext)' }}>
                {job.status === 'running' || job.status === 'pending'
                  ? '⟳ Research in progress…'
                  : `${job.status} — ${results.length} results`}
              </p>
            )}
            {results.map(r => (
              <div key={r.id} className="mb-3">
                <NewsCard
                  item={{
                    id: r.id,
                    title: r.title,
                    url: r.url ?? undefined,
                    snippet: r.snippet ?? undefined,
                    source_name: r.source,
                  }}
                />
                <GradeBar
                  resultId={r.id}
                  jobId={col1Content.jobId}
                  initialGrade={r.grade}
                  onGrade={(resultId, grade) => {
                    gradeResult(col1Content.jobId, resultId, grade).catch(() => {})
                  }}
                />
              </div>
            ))}
            {job?.status === 'completed' && results.length === 0 && (
              <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>No results found.</p>
            )}
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'Summary' && (
          <div className="text-xs p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            {job ? (
              <>
                <div className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>{job.query}</div>
                <div className="mb-1" style={{ color: 'var(--subtext)' }}>Status: {job.status}</div>
                <div style={{ color: 'var(--subtext)' }}>Results: {results.length}</div>
                {results.filter(r => r.source === 'qdrant').length > 0 && (
                  <div className="mt-2 text-[10px]" style={{ color: 'var(--muted)' }}>
                    {results.filter(r => r.source === 'qdrant').length} results from Qdrant memory
                  </div>
                )}
              </>
            ) : 'Loading…'}
          </div>
        )}

        {activeTab === 'Profiles' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Profile results appear here when LinkedIn plugin is active.</p>
        )}
        {activeTab === 'Social' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Social crawl results appear here.</p>
        )}
      </div>
    </div>
  )
}
