import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob, getJobResults, gradeResult } from '../../api/v3'
import { listPipelines, startPipelineRun, cancelPipelineRun, deletePipeline, listAllPipelineRuns, getPipelineRun } from '../../api/pipelines'
import NewsCard from './NewsCard'
import GradeBar from './GradeBar'

type Tab = 'Pipeline' | 'News' | 'Summary' | 'Profiles' | 'Social'
const TABS: Tab[] = ['Pipeline', 'News', 'Summary', 'Profiles', 'Social']

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

function PipelineTabContent() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const col1Content = useSessionStore(s => s.col1Content)
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })
  const { data: allRuns = [] } = useQuery({
    queryKey: ['pipeline-runs-all'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 5000,
  })

  const startRun = useMutation({
    mutationFn: startPipelineRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] }),
  })
  const pauseRun = useMutation({
    mutationFn: cancelPipelineRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] }),
  })
  const deleteRun = useMutation({
    mutationFn: deletePipeline,
    onSuccess: () => {
      setConfirmDeleteId(null)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] })
    },
  })

  const runId = col1Content?.type === 'pipeline_run' ? col1Content.runId : null

  if (pipelines.length === 0 && !runId) {
    return (
      <div className="text-center mt-12 px-4">
        <div style={{ fontSize: 28, marginBottom: 12 }}>⬡</div>
        <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text)' }}>Getting Started</p>
        <p className="text-xs mb-6" style={{ color: 'var(--muted)' }}>
          Create a pipeline to automate research, enrichment, and scoring workflows.
        </p>
        <button
          onClick={() => navigate('/pipelines')}
          style={{
            padding: '8px 16px',
            fontSize: 11,
            fontWeight: 600,
            borderRadius: 6,
            background: 'var(--accent)',
            color: 'var(--bg)',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          + Create A Pipeline
        </button>
      </div>
    )
  }

  return (
    <div className="p-3">
      {pipelines.map(pipeline => {
        const activeRun = allRuns.find(
          r => r.pipeline_id === pipeline.id && (r.status === 'running' || r.status === 'queued'),
        )
        const isSelected = runId && allRuns.find(r => r.id === runId && r.pipeline_id === pipeline.id)
        const isConfirming = confirmDeleteId === pipeline.id

        return (
          <div key={pipeline.id} className="mb-2">
            <div
              className="flex items-center justify-between px-3 py-2 rounded"
              style={{
                background: isSelected ? 'var(--panel2)' : 'var(--panel)',
                border: `1px solid ${isConfirming ? '#ef4444' : isSelected ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              <span
                className="text-xs font-medium truncate"
                style={{ color: 'var(--text)', cursor: 'pointer', flex: 1 }}
                onClick={() => navigate(`/pipelines/${pipeline.id}`)}
              >
                {pipeline.name}
              </span>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                {!isConfirming && (
                  <>
                    {activeRun ? (
                      <button
                        title="Pause (cancel run)"
                        onClick={() => pauseRun.mutate(activeRun.id)}
                        disabled={pauseRun.isPending}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#facc15' }}
                      >
                        ⏸
                      </button>
                    ) : (
                      <button
                        title="Run pipeline"
                        onClick={() => startRun.mutate(pipeline.id)}
                        disabled={startRun.isPending}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#4ade80' }}
                      >
                        ▶
                      </button>
                    )}
                    <button
                      title="Reset (clear selection)"
                      onClick={() => setCol1Content(null)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}
                    >
                      ↺
                    </button>
                    <button
                      title="Delete pipeline"
                      onClick={() => setConfirmDeleteId(pipeline.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#f87171' }}
                    >
                      🗑
                    </button>
                  </>
                )}
                {isConfirming && (
                  <>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      style={{
                        fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                        background: 'transparent', border: '1px solid var(--border)',
                        color: 'var(--muted)', cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => deleteRun.mutate(pipeline.id)}
                      disabled={deleteRun.isPending}
                      style={{
                        fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                        background: '#7f1d1d', border: '1px solid #ef4444',
                        color: '#fca5a5', cursor: 'pointer', opacity: deleteRun.isPending ? 0.6 : 1,
                      }}
                    >
                      {deleteRun.isPending ? 'Deleting…' : 'Delete'}
                    </button>
                  </>
                )}
              </div>
            </div>
            {isConfirming && (
              <div
                className="px-3 py-1 text-[10px] rounded-b"
                style={{ background: '#7f1d1d22', color: '#fca5a5', border: '1px solid #ef444433', borderTop: 'none', marginTop: -2 }}
              >
                This will permanently delete "{pipeline.name}" and all its runs.
              </div>
            )}
          </div>
        )
      })}

      {runId && (
        <div className="mt-4">
          <div className="text-[10px] font-semibold mb-2 tracking-widest" style={{ color: 'var(--muted)' }}>
            RUN RESULTS
          </div>
          <PipelineRunResults runId={runId} />
        </div>
      )}
    </div>
  )
}

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('Pipeline')
  const col1Content = useSessionStore(s => s.col1Content)

  // Auto-switch to Pipeline tab when a pipeline run is selected
  useEffect(() => {
    if (col1Content?.type === 'pipeline_run') setActiveTab('Pipeline')
  }, [col1Content])

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

      <div className="flex-1 overflow-y-auto">
        {activeTab === 'Pipeline' && <PipelineTabContent />}

        {activeTab === 'News' && (
          <div className="p-3">
            {!col1Content && (
              <div className="text-center mt-16">
                <p className="text-xs" style={{ color: 'var(--muted)' }}>
                  Send a message to the agent or tap a job in the live stream.
                </p>
              </div>
            )}

            {col1Content?.type === 'job' && (
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
                      jobId={(col1Content as { type: 'job'; jobId: string }).jobId}
                      initialGrade={r.grade}
                      onGrade={(resultId, grade) => {
                        gradeResult((col1Content as { type: 'job'; jobId: string }).jobId, resultId, grade).catch(() => {})
                      }}
                    />
                  </div>
                ))}
                {job?.status === 'completed' && results.length === 0 && (
                  <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>No results found.</p>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'Summary' && (
          <div className="p-3">
            {col1Content?.type === 'job' && (
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
          </div>
        )}

        {activeTab === 'Profiles' && (
          <div className="p-3">
            <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Profile results appear here when LinkedIn plugin is active.</p>
          </div>
        )}

        {activeTab === 'Social' && (
          <div className="p-3">
            <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Social crawl results appear here.</p>
          </div>
        )}
      </div>
    </div>
  )
}
