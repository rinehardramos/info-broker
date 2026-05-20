import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listJobs, getCoreSettings, listSessions, getSession, type JobOut, type AgentSession } from '../../api/v3'
import { listAllPipelineRuns, type PipelineRunSummary } from '../../api/pipelines'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { replayRunIntoStore } from '../../hooks/useReplay'
import JobItem from './JobItem'
import PipelineRunItem from './PipelineRunItem'
import { Skeleton } from '../ui/skeleton'
import { EmptyState } from '../ui/empty-state'
import { InlineError } from '../ui/inline-error'
import { useDebouncedLoading } from '../../hooks/useDebouncedLoading'

function SessionHistoryItem({ session }: { session: AgentSession }) {
  const setSessionId = useChatStore(s => s.setSessionId)
  const setGenesisQuery = useChatStore(s => s.setGenesisQuery)
  const clearMessages = useChatStore(s => s.clearMessages)
  const setMessages = useChatStore(s => s.setMessages)
  const [resumingId, setResumingId] = useState<string | null>(null)

  const resume = async () => {
    setResumingId(session.id)
    try {
      const full = await getSession(session.id)
      const thread = full.conversation_thread ?? []
      if (thread.length > 0) {
        const restoredMessages = thread.map((entry, i) => ({
          id: `restored-${i}`,
          role: (entry.role === 'assistant' ? 'agent' : entry.role) as 'user' | 'agent',
          content: entry.content,
        }))
        setMessages(restoredMessages)
      } else if (full.accumulated_summary) {
        setMessages([{
          id: 'summary-restored',
          role: 'agent',
          content: `📋 Session summary: ${full.accumulated_summary}`,
        }])
      } else {
        clearMessages()
      }
      setSessionId(session.id)
      setGenesisQuery(session.genesis_query)
    } catch {
      clearMessages()
      setSessionId(session.id)
      setGenesisQuery(session.genesis_query)
    } finally {
      setResumingId(null)
    }
  }

  const isResuming = resumingId === session.id

  const age = (() => {
    const d = Date.now() - new Date(session.created_at).getTime()
    if (d < 60_000) return 'now'
    if (d < 3_600_000) return `${Math.floor(d / 60_000)}m`
    if (d < 86_400_000) return `${Math.floor(d / 3_600_000)}h`
    return `${Math.floor(d / 86_400_000)}d`
  })()

  return (
    <button
      data-testid="history-session-item"
      onClick={resume}
      disabled={isResuming}
      title={isResuming ? 'Resuming…' : `Resume: "${session.genesis_query}"`}
      style={{
        width: '100%', textAlign: 'left', padding: '5px 6px',
        borderRadius: 5, border: '1px solid var(--border)',
        background: 'transparent', cursor: 'pointer',
        marginBottom: 3, transition: 'background 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--panel2)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
        <span style={{
          fontSize: 10, color: 'var(--text)', fontWeight: 400,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
        }}>
          {isResuming ? 'Resuming…' : session.genesis_query}
        </span>
        <span style={{ fontSize: 8, color: 'var(--muted)', flexShrink: 0 }}>{age}</span>
      </div>
      <div style={{ display: 'flex', gap: 5, marginTop: 2, flexWrap: 'wrap' }}>
        {session.entity_type && (
          <span style={{
            fontSize: 8, color: 'var(--accent)', background: 'var(--accent)10',
            padding: '0 4px', borderRadius: 3,
          }}>{session.entity_type}</span>
        )}
        <span style={{ fontSize: 8, color: 'var(--muted)' }}>{session.run_count}r · {session.turn_count}t</span>
      </div>
    </button>
  )
}

export default function LiveStream() {
  const qc = useQueryClient()
  const clearMessages = useChatStore(s => s.clearMessages)
  const sessionId = useChatStore(s => s.sessionId)
  const setCol1Content = useSessionStore(s => s.setCol1Content)

  const { data: coreSettings } = useQuery({
    queryKey: ['core-settings'],
    queryFn: getCoreSettings,
    staleTime: 60_000,
  })
  const retentionMs = Number(coreSettings?.settings['live_panel.retention_seconds'] ?? 600) * 1000

  const {
    data: jobs = [],
    isLoading: jobsLoading,
    isError: jobsError,
    error: jobsErrorObj,
    refetch: refetchJobs,
  } = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 30_000 })
  const {
    data: pipelineRuns = [],
    isLoading: pipelineRunsLoading,
  } = useQuery({
    queryKey: ['pipeline-runs-all'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 10_000,
  })
  const {
    data: sessions = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrorObj,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ['agent-sessions'],
    queryFn: listSessions,
    refetchInterval: 30_000,
  })
  const showLiveSkeleton = useDebouncedLoading(jobsLoading || pipelineRunsLoading)
  const showSessionsSkeleton = useDebouncedLoading(sessionsLoading)

  const [liveEvents, setLiveEvents] = useState<JobOut[]>([])
  const [livePipelineEvents, setLivePipelineEvents] = useState<(Partial<PipelineRunSummary> & { id: string })[]>([])

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
        qc.invalidateQueries({ queryKey: ['agent-sessions'] })
      }
    }

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

  const _TERMINAL = new Set(['failed', 'succeeded', 'cancelled', 'awaiting_input', 'confirm_pending'])

  const mergedPipelineRuns: PipelineRunSummary[] = pipelineRuns
    .map(r => {
      const live = livePipelineEvents.find(l => l.id === r.id)
      if (!live) return r
      // Terminal DB status always wins — prevents zombie "running" display after server restart
      if (_TERMINAL.has(r.status)) return r
      return { ...r, ...live } as PipelineRunSummary
    })
    .slice(0, 20)

  const visibleJobs = mergedJobs.filter(j => new Date(j.created_at).getTime() > cutoff)
  const visibleRuns = mergedPipelineRuns.filter(r =>
    new Date(r.started_at).getTime() > cutoff &&
    !_TERMINAL.has(r.status)
  )

  const hasLive = visibleJobs.length > 0 || visibleRuns.length > 0

  const oneDayAgo = Date.now() - 86_400_000
  const reviewRuns = pipelineRuns
    .filter(r =>
      r.status === 'succeeded' &&
      r.trigger_type === 'agent_is' &&
      new Date(r.started_at).getTime() > oneDayAgo,
    )
    .slice(0, 5)

  const timeAgo = (iso: string) => {
    const d = Date.now() - new Date(iso).getTime()
    if (d < 60_000) return 'now'
    if (d < 3_600_000) return `${Math.floor(d / 60_000)}m ago`
    if (d < 86_400_000) return `${Math.floor(d / 3_600_000)}h ago`
    return `${Math.floor(d / 86_400_000)}d ago`
  }

  return (
    <div className="flex flex-col h-full">

      {/* ── Live section (top half) ── */}
      <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--border)' }}>
        <div
          style={{
            height: 30, display: 'flex', alignItems: 'center', padding: '0 10px',
            borderBottom: '1px solid var(--border)', flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.06em' }}>LIVE</span>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {visibleJobs.length > 0 && (
            <>
              <div className="px-1 pb-1 text-[9px] font-semibold tracking-widest" style={{ color: 'var(--muted)' }}>RESEARCH</div>
              {visibleJobs.map(job => <JobItem key={job.id} job={job} />)}
            </>
          )}
          {visibleRuns.length > 0 && (
            <div className={visibleJobs.length > 0 ? 'mt-3' : ''}>
              <div className="px-1 pb-1 text-[9px] font-semibold tracking-widest" style={{ color: 'var(--muted)' }}>PIPELINES</div>
              {visibleRuns.map(run => <PipelineRunItem key={run.id} run={run} />)}
            </div>
          )}
          {!hasLive && showLiveSkeleton && (
            <div className="space-y-1.5 px-1 mt-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          )}
          {!hasLive && !showLiveSkeleton && jobsError && (
            <InlineError
              title="Couldn't load active jobs"
              message={(jobsErrorObj as Error | undefined)?.message}
              onRetry={() => refetchJobs()}
              inline
              className="mt-3 px-1 text-[10px]"
            />
          )}
          {!hasLive && !showLiveSkeleton && !jobsError && (
            <EmptyState
              title="No active jobs"
              hint="Research and pipelines you start will appear here while they run."
              compact
              className="text-[10px]"
            />
          )}
        </div>
      </div>

      {/* ── History section ── */}
      <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--border)' }}>
        <div
          style={{
            height: 30, display: 'flex', alignItems: 'center', padding: '0 10px',
            borderBottom: '1px solid var(--border)', flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.06em' }}>HISTORY</span>
          {sessions.length > 0 && (
            <span style={{
              marginLeft: 5, fontSize: 8, fontWeight: 600,
              background: 'var(--accent)', color: 'var(--bg)',
              borderRadius: 8, padding: '1px 5px',
            }}>{sessions.length}</span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {sessions.length === 0 && showSessionsSkeleton && (
            <div className="space-y-1.5 px-1 mt-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          )}
          {sessions.length === 0 && !showSessionsSkeleton && sessionsError && (
            <InlineError
              title="Couldn't load history"
              message={(sessionsErrorObj as Error | undefined)?.message}
              onRetry={() => refetchSessions()}
              inline
              className="mt-3 px-1 text-[10px]"
            />
          )}
          {sessions.length === 0 && !showSessionsSkeleton && !sessionsError && (
            <EmptyState
              title="No sessions yet"
              hint="Past investigations show up here."
              compact
              className="text-[10px]"
            />
          )}
          {sessions.length > 0 && sessions.map(s => <SessionHistoryItem key={s.id} session={s} />)}
        </div>
      </div>

      {/* ── Review section ── */}
      <div style={{ flex: '1 1 0', minHeight: 120, display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            height: 30, display: 'flex', alignItems: 'center', padding: '0 10px',
            borderBottom: '1px solid var(--border)', flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: '#facc15', letterSpacing: '0.06em' }}>REVIEW</span>
          {reviewRuns.length > 0 && (
            <span style={{
              marginLeft: 5, fontSize: 8, fontWeight: 600,
              background: '#facc15', color: '#000',
              borderRadius: 8, padding: '1px 5px',
            }}>{reviewRuns.length}</span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {reviewRuns.length === 0 ? (
            <EmptyState
              title="No runs to review"
              hint="Runs that need grading or follow-up land here."
              compact
              className="text-[10px]"
            />
          ) : (
            reviewRuns.map(run => (
              <div
                key={run.id}
                style={{
                  background: 'var(--panel2)',
                  borderLeft: '3px solid #facc15',
                  borderRadius: 5,
                  padding: '5px 6px',
                  marginBottom: 4,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{
                    fontSize: 10, color: 'var(--text)', fontWeight: 400,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                  }}>
                    {run.query ? (run.query.length > 35 ? run.query.slice(0, 35) + '…' : run.query) : '(no query)'}
                  </span>
                  <span style={{ fontSize: 8, color: 'var(--muted)', flexShrink: 0 }}>
                    {timeAgo(run.started_at)}
                  </span>
                  <button
                    onClick={() => setCol1Content({ type: 'pipeline_run', runId: run.id })}
                    title="Open in Results panel"
                    style={{
                      flexShrink: 0, padding: '1px 5px', borderRadius: 3,
                      fontSize: 9, fontWeight: 600,
                      border: '1px solid #facc1560',
                      background: '#facc1510',
                      color: '#facc15',
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = '#facc1525'
                      e.currentTarget.style.borderColor = '#facc15'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = '#facc1510'
                      e.currentTarget.style.borderColor = '#facc1560'
                    }}
                  >
                    →
                  </button>
                </div>
                <div style={{ marginTop: 2, display: 'flex', gap: 5 }}>
                  {run.pipeline_name && (
                    <span style={{ fontSize: 8, color: 'var(--muted)' }}>{run.pipeline_name}</span>
                  )}
                  <span style={{ fontSize: 8, color: 'var(--muted)' }}>{run.steps_done} / {run.step_count} steps</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* ── New Session button — shared footer below all three sections ── */}
        <div style={{
          flexShrink: 0, padding: '6px 8px',
          borderTop: '1px solid var(--border)',
        }}>
          <button
            onClick={clearMessages}
            title="Start a new investigation session"
            style={{
              width: '100%', padding: '6px 0', borderRadius: 6,
              fontSize: 10, fontWeight: 600, letterSpacing: '0.04em',
              border: `1px solid ${sessionId ? '#a78bfa60' : 'var(--border)'}`,
              background: sessionId ? '#a78bfa15' : 'transparent',
              color: sessionId ? '#a78bfa' : 'var(--muted)',
              cursor: 'pointer', transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = '#a78bfa20'
              e.currentTarget.style.borderColor = '#a78bfa'
              e.currentTarget.style.color = '#a78bfa'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = sessionId ? '#a78bfa15' : 'transparent'
              e.currentTarget.style.borderColor = sessionId ? '#a78bfa60' : 'var(--border)'
              e.currentTarget.style.color = sessionId ? '#a78bfa' : 'var(--muted)'
            }}
          >
            <span style={{ fontSize: 13, lineHeight: 1 }}>+</span>
            New Session
          </button>
        </div>
      </div>
    </div>
  )
}
