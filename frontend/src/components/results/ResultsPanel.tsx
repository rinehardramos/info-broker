import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, useQueries } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { useChatStore } from '../../stores/chatStore'
import { listPipelines, startPipelineRun, cancelPipelineRun, deletePipeline, listAllPipelineRuns, getPipelineRun, createPipeline, type ResearchTrail, type ResearchFinding } from '../../api/pipelines'
import { sendMessage, runAnalyzer, submitFindingFeedback, getRunFeedback, exportResearch } from '../../api/v3'
import { ResearchFlow } from './ResearchFlow'
import { useWebSocket } from '../../hooks/useWebSocket'
import { AnalysisPanel } from './AnalysisPanel'
import { ActionDrawer } from './ActionDrawer'
import { InvestigationBreakdown } from './InvestigationBreakdown'
import { Sparkles, ArrowDownToLine, Save, RefreshCw, RotateCcw, Layers, Loader2, Download, FileText, FileSpreadsheet } from 'lucide-react'

// Tab is either the static 'Pipeline' tab or a dynamic run tab identified by run ID
type Tab = 'Pipeline' | `run:${string}`

// ---------------------------------------------------------------------------
// SwipeToDelete — swipe left to reveal delete action
// ---------------------------------------------------------------------------

const SWIPE_THRESHOLD = 80
const SWIPE_DEAD_ZONE = 10

function SwipeToDelete({ children, onDelete }: { children: React.ReactNode; onDelete: () => void }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    let startX = 0
    let currentX = 0
    let swiped = false

    const begin = (x: number) => {
      startX = x; currentX = 0; swiped = false
      el.style.transition = ''
    }
    const move = (x: number) => {
      const dx = x - startX
      currentX = Math.min(0, dx)
      if (currentX < -SWIPE_DEAD_ZONE) swiped = true
      if (swiped) el.style.transform = `translateX(${currentX}px)`
    }
    const end = () => {
      if (swiped && currentX < -SWIPE_THRESHOLD) {
        el.style.transition = 'transform 0.2s ease, opacity 0.2s ease'
        el.style.transform = 'translateX(-100%)'
        el.style.opacity = '0'
        setTimeout(onDelete, 200)
      } else if (swiped) {
        el.style.transition = 'transform 0.2s ease'
        el.style.transform = 'translateX(0)'
      }
      const wasSwiped = swiped
      swiped = false
      setTimeout(() => { el.style.transition = '' }, 250)
      return wasSwiped
    }

    // --- Touch events (mobile) ---
    const onTouchStart = (e: TouchEvent) => begin(e.touches[0].clientX)
    const onTouchMove = (e: TouchEvent) => move(e.touches[0].clientX)
    const onTouchEnd = () => end()

    // --- Mouse events (desktop) — mousedown/move/up don't block click synthesis ---
    let mouseDown = false
    const onMouseDown = (e: MouseEvent) => { mouseDown = true; begin(e.clientX) }
    const onMouseMove = (e: MouseEvent) => { if (mouseDown) move(e.clientX) }
    const onMouseUp = () => { mouseDown = false; end() }
    // Block click only if a swipe happened (capture phase, before React handlers)
    const onClickCapture = (e: MouseEvent) => {
      if (swiped) { e.stopPropagation(); e.preventDefault() }
    }

    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: true })
    el.addEventListener('touchend', onTouchEnd)
    el.addEventListener('mousedown', onMouseDown)
    el.addEventListener('mousemove', onMouseMove)
    el.addEventListener('mouseup', onMouseUp)
    el.addEventListener('click', onClickCapture, true)

    return () => {
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('mousedown', onMouseDown)
      el.removeEventListener('mousemove', onMouseMove)
      el.removeEventListener('mouseup', onMouseUp)
      el.removeEventListener('click', onClickCapture, true)
    }
  }, [onDelete])

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 6 }}>
      {/* Delete label behind the card */}
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
        justifyContent: 'flex-end', paddingRight: 16,
        background: '#7f1d1d', color: '#fca5a5', fontSize: 11, fontWeight: 700,
        borderRadius: 6,
      }}>
        DELETE
      </div>
      <div ref={ref} style={{ position: 'relative' }}>
        {children}
      </div>
    </div>
  )
}

const STEP_STATUS_COLOR: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
}

function PipelineRunResults({ runId, onNavigateRun }: { runId: string; onNavigateRun?: (newRunId: string) => void }) {
  const { data: run, isLoading } = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => getPipelineRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      // Poll while active or awaiting user action (so re-runs and confirmations clear properly)
      const active = ['running', 'queued', 'confirm_pending', 'awaiting_input']
      return status && active.includes(status) ? 3000 : false
    },
  })
  const [goingDeeper, setGoingDeeper] = useState(false)

  if (isLoading) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Loading…</p>
  }

  if (!run) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Run not found.</p>
  }

  // IS research run — completed with findings
  if (run.trigger_type === 'agent_is' && run.research) {
    return (
      <ResearchResults
        research={run.research}
        status={run.status}
        runId={runId}
        goingDeeper={goingDeeper}
        onGoDeeper={async (leads) => {
          setGoingDeeper(true)
          try {
            const deeper = leads.join('; ')
            const resp = await sendMessage(`Go deeper: ${deeper}`, undefined, true, runId ?? undefined)
            if (resp?.job_id && onNavigateRun) onNavigateRun(resp.job_id)
          } finally {
            setGoingDeeper(false)
          }
        }}
      />
    )
  }

  // IS research run — failed with no findings
  if (run.trigger_type === 'agent_is' && run.status === 'failed' && !run.research) {
    return (
      <div className="p-3">
        <div
          className="rounded p-3 mb-3 text-xs"
          style={{ background: '#ef444415', border: '1px solid #ef444433' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span style={{ fontSize: 8, color: '#f87171' }}>◆</span>
            <span style={{ color: '#f87171', fontWeight: 600 }}>IS Research — Failed</span>
          </div>
          {run.error_message ? (
            <div>
              <div style={{ color: '#fca5a5', fontSize: 10, marginBottom: 6 }}>
                The research brain encountered an error:
              </div>
              <div
                className="p-2 rounded"
                style={{
                  background: '#0f172a', border: '1px solid #1e293b',
                  fontFamily: 'monospace', fontSize: 10, color: '#fca5a5',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}
              >
                {run.error_message}
              </div>
            </div>
          ) : (
            <p style={{ color: '#fca5a5', fontSize: 10 }}>
              Research failed with no error details captured. Check server logs for more information.
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <button
              onClick={async () => {
                try {
                  const query = run.query || 'Retry research'
                  const resp = await sendMessage(query, undefined, true)
                  if (resp?.job_id && onNavigateRun) onNavigateRun(resp.job_id)
                } catch {}
              }}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: 'var(--accent)', color: '#fff', border: 'none',
                fontSize: 11, fontWeight: 600, padding: '8px 14px', borderRadius: 8,
                cursor: 'pointer',
              }}
            >
              <RotateCcw size={13} />
              Retry{run.query ? `: "${run.query.slice(0, 35)}${run.query.length > 35 ? '...' : ''}"` : ''}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // IS research awaiting user confirmation
  if (run.trigger_type === 'agent_is' && run.status === 'confirm_pending') {
    return (
      <div className="p-3 flex flex-col h-full">
        <div
          className="rounded p-3 mb-3 text-xs"
          style={{ background: 'var(--panel2)', border: '1px solid #f59e0b' }}
        >
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 8, color: '#f59e0b' }}>◆</span>
            <span style={{ color: '#f59e0b', fontWeight: 600 }}>IS Research — awaiting your confirmation</span>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 10, marginTop: 4 }}>
            A result was found. Check the chat to confirm or reject it.
          </p>
        </div>
      </div>
    )
  }

  // IS research run — still running, show live streaming view
  if (run.trigger_type === 'agent_is' && (run.status === 'queued' || run.status === 'running')) {
    return (
      <div className="p-3 flex flex-col h-full">
        <div
          className="rounded p-3 mb-3 text-xs"
          style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 8, color: '#a78bfa' }}>◆</span>
            <span style={{ color: '#a78bfa', fontWeight: 600 }}>IS Research — {run.status}</span>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: 10, marginTop: 4 }}>
            Brain is actively researching. Tool calls stream below in real-time.
          </p>
        </div>
        <div className="flex-1 overflow-auto">
          <ResearchFlow runId={runId ?? undefined} />
        </div>
      </div>
    )
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
        {run.status === 'failed' && (run as any).error_message && (
          <div
            className="mt-2 p-2 rounded text-xs"
            style={{ background: '#ef444415', border: '1px solid #ef444433', color: '#fca5a5' }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Error Details</div>
            <div style={{ fontFamily: 'monospace', fontSize: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {(run as any).error_message}
            </div>
          </div>
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

// ---------------------------------------------------------------------------
// IS Research Results
// ---------------------------------------------------------------------------

const CONFIDENCE_COLORS: Record<string, string> = {
  high: '#4ade80',
  medium: '#facc15',
  low: '#f87171',
}

function confidenceLevel(score: number): 'high' | 'medium' | 'low' {
  if (score >= 75) return 'high'
  if (score >= 50) return 'medium'
  return 'low'
}

// ---------------------------------------------------------------------------
// Source Integrity Badge — compact header indicator for deception risk
// ---------------------------------------------------------------------------

function SourceIntegrityBadge({ analysis }: { analysis: any }) {
  if (!analysis) return null
  const risk: number = analysis.deception_risk ?? 0
  const conflicts: any[] = analysis.conflicts ?? []

  const effectiveRisk = conflicts.length > 0 && risk < 0.3 ? 0.3 : risk

  let label: string
  let color: string
  let bg: string

  if (effectiveRisk > 0.5) {
    label = '⚠ Source concerns'
    color = '#f87171'
    bg = '#f8717122'
  } else if (effectiveRisk >= 0.3) {
    label = '⚠ Check sources'
    color = '#facc15'
    bg = '#facc1522'
  } else {
    label = '✓ Sources verified'
    color = '#4ade80'
    bg = '#4ade8022'
  }

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontSize: 9, fontWeight: 600,
      color, background: bg,
      border: `1px solid ${color}55`,
      borderRadius: 4, padding: '1px 6px', marginTop: 4,
    }}>
      {label}
    </span>
  )
}

// Module-level caches: persist across tab switches / remounts
const _analysisCache = new Map<string, any>()
const _analyzingRuns = new Set<string>()

function ResearchResults({
  research,
  status,
  runId,
  goingDeeper,
  onGoDeeper,
}: {
  research: ResearchTrail
  status: string
  runId: string | null
  goingDeeper: boolean
  onGoDeeper: (leads: string[]) => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [pipelineSaved, setPipelineSaved] = useState(false)
  const [savingPipeline, setSavingPipeline] = useState(false)
  // Initialize from: module cache > server DB > null
  // Initialize analyzing from: module set > DB status marker (only if actively in _analyzingRuns, not stuck DB state)
  const _rid = runId ?? ''
  const initAnalysis = _analysisCache.get(_rid) ?? (research.analysis && !(research.analysis as any)._status ? research.analysis : null)
  const initAnalyzing = _analyzingRuns.has(_rid)

  const [analyzing, setAnalyzing] = useState(!!initAnalyzing)
  const [analysis, setAnalysis] = useState<any>(initAnalysis)
  const [feedback, setFeedback] = useState<Record<number, { src: string; cred: number }>>({})
  const [openRating, setOpenRating] = useState<Record<number, boolean>>({})
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    if (runId) {
      getRunFeedback(runId).then(fb => {
        if (!mountedRef.current) return
        const mapped: Record<number, { src: string; cred: number }> = {}
        Object.entries(fb).forEach(([idx, val]) => {
          const reason = val.reason ?? ''
          if (reason.length >= 2) {
            const src = reason[0]
            const cred = parseInt(reason[1])
            if ('ABCDEF'.includes(src) && cred >= 1 && cred <= 6) {
              mapped[Number(idx)] = { src, cred }
            }
          }
        })
        setFeedback(mapped)
      }).catch(() => {})
    }
  }, [runId])

  // Poll for analysis completion when analyzing is in progress
  useEffect(() => {
    if (!analyzing || !runId) return
    const interval = setInterval(() => {
      getPipelineRun(runId).then(run => {
        if (!mountedRef.current) return
        const a = run?.research?.analysis
        if (a && !(a as any)._status) {
          // Analysis complete — has real data (no _status marker)
          _analysisCache.set(runId, a)
          _analyzingRuns.delete(runId)
          setAnalysis(a)
          setAnalyzing(false)
        } else if (a && (a as any)._status === 'failed') {
          _analyzingRuns.delete(runId)
          setAnalyzing(false)
        }
      }).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [analyzing, runId])

  // Also listen for WS events (faster than polling when connected)
  const handleWsEvent = useCallback((event: any) => {
    if (!runId) return
    if ((event.type === 'analysis.completed' || event.type === 'analysis.failed') && event.run_id === runId) {
      _analyzingRuns.delete(runId)
      getPipelineRun(runId).then(run => {
        if (!mountedRef.current) return
        const a = run?.research?.analysis
        if (a && !(a as any)._status) {
          _analysisCache.set(runId, a)
          setAnalysis(a)
        }
        setAnalyzing(false)
      }).catch(() => {})
    }
    // Re-run after "No, try another" resets the run to queued/running.
    // Polling was disabled while confirm_pending — force a refetch so the amber box clears.
    if (event.type === 'job.update' && (event.run_id === runId || event.job_id === runId)) {
      qc.invalidateQueries({ queryKey: ['pipeline-run', runId] })
    }
  }, [runId, qc])

  useWebSocket(handleWsEvent)

  const handleAnalyze = async (context?: string) => {
    setAnalyzing(true)
    if (runId) _analyzingRuns.add(runId)
    try {
      await runAnalyzer(research.findings, undefined, context || undefined, research.query, runId || undefined)
    } catch (err) {
      console.error('Analysis failed:', err)
      if (runId) _analyzingRuns.delete(runId)
      if (mountedRef.current) setAnalyzing(false)
    }
  }

  const handleExport = async (format: 'pdf' | 'csv' | 'xlsx') => {
    if (!runId) return
    setExporting(true)
    setExportOpen(false)
    try {
      const result = await exportResearch(runId, format)
      window.open(result.url, '_blank')
    } catch (err) {
      console.error('Export failed:', err)
    } finally {
      setExporting(false)
    }
  }

  const admiraltyToScore = (src: string, cred: number): number => {
    if ((src === 'A' || src === 'B') && (cred === 1 || cred === 2)) return 1
    if ((src === 'D' || src === 'E') && (cred === 4 || cred === 5)) return -1
    if (src === 'E' && cred === 5) return -1
    if (src === 'D' && cred === 4) return -1
    return 0
  }

  const admiraltyColor = (src: string, cred: number): string => {
    if ((src === 'A' || src === 'B') && (cred === 1 || cred === 2)) return '#4ade80'
    if ((src === 'C' && cred === 2) || (src === 'B' && cred === 3) || (src === 'C' && cred === 3)) return '#facc15'
    if ((src === 'D' && (cred === 3 || cred === 4)) || (src === 'C' && cred === 4)) return '#fb923c'
    if ((src === 'E' || src === 'D') && (cred === 4 || cred === 5)) return '#f87171'
    if (src === 'F' || cred === 6 || cred === 5) return '#f87171'
    if (src === 'F') return '#6b7280'
    return '#6b7280'
  }

  const handleFeedback = async (index: number, src: string, cred: number, title: string) => {
    setFeedback(prev => ({ ...prev, [index]: { src, cred } }))
    setOpenRating(prev => ({ ...prev, [index]: false }))
    if (runId) {
      const score = admiraltyToScore(src, cred)
      const reason = `${src}${cred}`
      await submitFindingFeedback(runId, index, score, reason, title)
    }
  }
  const { findings, trail } = research
  // Always allow Go Deeper when findings exist — use trail leads if available, else derive from findings
  const canGoDeeper = findings.length > 0
  const hasPipeline = findings.length > 0

  async function handleSavePipeline() {
    setSavingPipeline(true)
    try {
      const sp = research.suggested_pipeline
      let pipelineData: { name: string; description: string; nodes: object[]; edges: object[] }
      if (sp && sp.nodes?.length > 0) {
        const nodeIds = sp.nodes.map(() => crypto.randomUUID())
        pipelineData = {
          name: sp.name,
          description: `Generated from IS research: "${research.query}"`,
          nodes: sp.nodes.map((n: any, i: number) => ({
            id: nodeIds[i],
            node_type: n.node_type,
            label: n.label,
            config: n.config ?? {},
            position_y: i,
          })),
          edges: (sp.edges ?? []).map((e: any) => ({
            source_node_id: nodeIds[e.source_index],
            target_node_id: nodeIds[e.target_index],
          })),
        }
      } else {
        // No suggested pipeline — generate a default IS research pipeline
        const nodeId = crypto.randomUUID()
        pipelineData = {
          name: `IS Research: ${research.query?.slice(0, 50) ?? 'Research'}`,
          description: `Saved from IS research run. Query: "${research.query}"`,
          nodes: [{
            id: nodeId,
            node_type: 'intelligent_search',
            label: 'Intelligent Search',
            config: { query: research.query ?? '' },
            position_y: 0,
          }],
          edges: [],
        }
      }
      const result = await createPipeline(pipelineData as any)
      setPipelineSaved(true)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      navigate(`/pipeline/${result.id}`)
    } catch (err) {
      console.error('Failed to save pipeline:', err)
    } finally {
      setSavingPipeline(false)
    }
  }

  return (
    <div className="p-3">
      {/* Header */}
      <div
        className="rounded p-3 mb-3 text-xs"
        style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span style={{ fontSize: 8, color: STEP_STATUS_COLOR[status] ?? 'var(--muted)' }}>◆</span>
          <span style={{ color: '#a78bfa', fontWeight: 700, fontSize: 10 }}>Intelligent Search</span>
          <span style={{ color: STEP_STATUS_COLOR[status] ?? 'var(--muted)', fontSize: 10 }}>
            {status}
          </span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--subtext)', marginTop: 4 }}>
          {research.query}
        </div>
        {runId && (
          <button
            onClick={() => { navigator.clipboard.writeText(runId); }}
            title="Click to copy run ID"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 4,
              fontSize: 9, fontFamily: 'monospace', color: 'var(--muted)',
              background: 'var(--panel)', border: '1px solid var(--border)',
              padding: '1px 6px', borderRadius: 4, cursor: 'pointer',
            }}
          >
            ID: {runId.slice(0, 8)} <span style={{ fontSize: 8, opacity: 0.6 }}>copy</span>
          </button>
        )}
        {research.entity_type && research.entity_type !== 'unknown' && (
          <span
            style={{
              display: 'inline-block', marginTop: 4, fontSize: 9, fontWeight: 600,
              background: '#a78bfa22', color: '#a78bfa', padding: '1px 6px', borderRadius: 4,
            }}
          >
            {research.entity_type}
          </span>
        )}
        <SourceIntegrityBadge analysis={(research as any).analysis} />
      </div>

      {/* Tree stats */}
      {trail.total_branches != null && trail.total_branches > 0 && (
        <div className="flex gap-3 mb-3 text-[9px]" style={{ color: 'var(--muted)' }}>
          <span>{trail.total_branches} branches</span>
          <span style={{ color: '#4ade80' }}>{trail.resolved} resolved</span>
          {(trail.dead_ends ?? 0) > 0 && <span style={{ color: '#f87171' }}>{trail.dead_ends} dead ends</span>}
          {(trail.needs_tool ?? 0) > 0 && <span style={{ color: '#fb923c' }}>{trail.needs_tool} needs tool</span>}
          <span>depth {trail.max_depth_reached}</span>
        </div>
      )}

      {/* Findings */}
      <div className="text-[10px] font-semibold mb-2 tracking-widest" style={{ color: 'var(--muted)' }}>
        FINDINGS ({findings.length})
      </div>
      <div className="flex flex-col gap-2 mb-3">
        {findings.length === 0 && (
          <p className="text-xs" style={{ color: 'var(--muted)' }}>
            {status === 'running' ? 'Searching...' : 'No findings.'}
          </p>
        )}
        {findings.map((f, i) => {
          const conf = f.confidence ?? 0
          const level = confidenceLevel(conf)
          const isError = (f as any).error_flagged === true || (f as any).finding_type === 'error'
          return (
            <div
              key={i}
              className="rounded p-3 text-xs"
              style={{
                background: 'var(--panel2)',
                border: '1px solid var(--border)',
                borderLeft: isError ? '3px solid #f87171' : undefined,
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  title={
                    isError
                      ? `Error: ${(f as any).title || 'Tool call failed'}`
                      : (f as any).confidence_reason || (f as any).ai_score_reason || (f as any).score_reason || (f as any).reason || `Confidence: ${conf}%`
                  }
                  style={{
                    fontSize: 9, fontWeight: 700,
                    color: isError ? '#f87171' : CONFIDENCE_COLORS[level],
                    cursor: 'help',
                  }}
                >
                  {isError ? '0% (error)' : `${conf}%`}
                </span>
                {isError && (
                  <span
                    style={{
                      fontSize: 8, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                      background: '#f8717122', color: '#f87171', border: '1px solid #f8717144',
                    }}
                  >
                    Error
                  </span>
                )}
                <span style={{ color: 'var(--subtext)', fontWeight: 600, opacity: isError ? 0.6 : 1 }}>
                  {f.title ?? 'Finding'}
                </span>
                {f.branch && (
                  <span style={{ color: 'var(--muted)', fontSize: 9, marginLeft: 'auto' }}>
                    {f.branch} d{f.depth}
                  </span>
                )}
              </div>
              {f.content && (
                <p style={{ color: 'var(--text)', fontSize: 10, lineHeight: 1.5, marginTop: 4, opacity: isError ? 0.5 : 1 }}>
                  {f.content}
                </p>
              )}
              {/* Multimedia preview — YouTube embed or image detected from URL */}
              {(() => {
                const mediaUrl = (f as any).image_url || (f as any).thumbnail_url ||
                  (f.url && /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(f.url) ? f.url : null)
                const ytMatch = f.url && f.url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/)
                const ytId = ytMatch ? ytMatch[1] : null
                if (ytId) return (
                  <div style={{ marginTop: 6, borderRadius: 6, overflow: 'hidden', maxWidth: 320 }}>
                    <iframe
                      src={`https://www.youtube-nocookie.com/embed/${ytId}`}
                      width="320" height="180"
                      style={{ display: 'block', border: 'none', borderRadius: 6 }}
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      loading="lazy"
                      title={f.title ?? 'Video'}
                    />
                  </div>
                )
                if (mediaUrl) return (
                  <div style={{ marginTop: 6 }}>
                    <img
                      src={mediaUrl}
                      alt={f.title ?? 'Media'}
                      loading="lazy"
                      style={{ maxWidth: 320, maxHeight: 200, borderRadius: 6, border: '1px solid var(--border)', display: 'block' }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  </div>
                )
                return null
              })()}
              <div className="flex items-center gap-2 mt-2" style={{ fontSize: 9, color: 'var(--muted)', opacity: isError ? 0.6 : 1 }}>
                {f.source && <span>{f.source}</span>}
                {f.source_class && (() => {
                  const SC_COLORS: Record<string, string> = {
                    live_search:        '#4ade80',
                    prior_research:     '#60a5fa',
                    primary_official:   '#a78bfa',
                    primary_self:       '#facc15',
                    training_generated: '#f87171',
                  }
                  const c = SC_COLORS[f.source_class] ?? '#94a3b8'
                  return (
                    <span style={{
                      fontSize: 8, padding: '1px 4px', borderRadius: 3,
                      background: `${c}26`, color: c, fontWeight: 600,
                    }}>
                      {f.source_class.replace(/_/g, ' ')}
                    </span>
                  )
                })()}
                {f.url && (
                  <a
                    href={f.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#60a5fa', textDecoration: 'none' }}
                  >
                    link
                  </a>
                )}
              </div>
              <div style={{ marginTop: 4 }}>
                {/* Admiralty Code rating badge/toggle */}
                <button
                  onClick={() => setOpenRating(prev => ({ ...prev, [i]: !prev[i] }))}
                  style={{
                    background: feedback[i]
                      ? `${admiraltyColor(feedback[i].src, feedback[i].cred)}22`
                      : 'transparent',
                    border: `1px solid ${feedback[i] ? admiraltyColor(feedback[i].src, feedback[i].cred) : 'var(--border)'}`,
                    color: feedback[i] ? admiraltyColor(feedback[i].src, feedback[i].cred) : 'var(--muted)',
                    fontSize: 9, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
                    fontWeight: feedback[i] ? 700 : 400, letterSpacing: feedback[i] ? 0.5 : 0,
                  }}
                >
                  {feedback[i] ? `${feedback[i].src}${feedback[i].cred}` : 'Rate'}
                </button>

                {/* Inline rating panel */}
                {openRating[i] && (
                  <div style={{
                    marginTop: 4, padding: '6px 8px', borderRadius: 6,
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    display: 'inline-flex', flexDirection: 'column', gap: 4,
                  }}>
                    {/* Source reliability row */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ fontSize: 8, color: 'var(--muted)', width: 14, flexShrink: 0 }}>SRC</span>
                      {['A', 'B', 'C', 'D', 'E', 'F'].map(s => (
                        <button
                          key={s}
                          onClick={() => {
                            if (feedback[i]?.cred) {
                              handleFeedback(i, s, feedback[i].cred, f.title ?? '')
                            } else {
                              setFeedback(prev => ({ ...prev, [i]: { src: s, cred: feedback[i]?.cred ?? 0 } }))
                            }
                          }}
                          style={{
                            width: 20, height: 20, fontSize: 9, borderRadius: 3, cursor: 'pointer',
                            fontWeight: 700,
                            background: feedback[i]?.src === s ? '#60a5fa33' : 'transparent',
                            border: `1px solid ${feedback[i]?.src === s ? '#60a5fa' : 'var(--border)'}`,
                            color: feedback[i]?.src === s ? '#60a5fa' : 'var(--muted)',
                          }}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                    {/* Credibility row */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ fontSize: 8, color: 'var(--muted)', width: 14, flexShrink: 0 }}>CRD</span>
                      {[1, 2, 3, 4, 5, 6].map(c => (
                        <button
                          key={c}
                          onClick={() => {
                            if (feedback[i]?.src) {
                              handleFeedback(i, feedback[i].src, c, f.title ?? '')
                            } else {
                              setFeedback(prev => ({ ...prev, [i]: { src: feedback[i]?.src ?? '', cred: c } }))
                            }
                          }}
                          style={{
                            width: 20, height: 20, fontSize: 9, borderRadius: 3, cursor: 'pointer',
                            fontWeight: 700,
                            background: feedback[i]?.cred === c ? '#a78bfa33' : 'transparent',
                            border: `1px solid ${feedback[i]?.cred === c ? '#a78bfa' : 'var(--border)'}`,
                            color: feedback[i]?.cred === c ? '#a78bfa' : 'var(--muted)',
                          }}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Investigation Breakdown scorecard */}
      {runId && <InvestigationBreakdown runId={runId} />}

      {/* Branches */}
      {trail.branches && trail.branches.length > 0 && (
        <>
          <div className="text-[10px] font-semibold mb-2 tracking-widest" style={{ color: 'var(--muted)' }}>
            BRANCHES
          </div>
          <div className="flex flex-wrap gap-1 mb-3">
            {trail.branches.map((b, i) => {
              const statusColor = b.status === 'fruit' ? '#4ade80'
                : b.status === 'dead_end' ? '#f87171'
                : b.status === 'needs_tool' ? '#fb923c'
                : '#facc15'
              return (
                <span
                  key={i}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    fontSize: 9, padding: '2px 6px', borderRadius: 4,
                    background: `${statusColor}11`, color: statusColor, border: `1px solid ${statusColor}33`,
                  }}
                  title={b.reason ?? b.status}
                >
                  {b.name} ({b.findings_count})
                </span>
              )
            })}
          </div>
        </>
      )}

      {/* Analyze button — shown before analysis is done (or when previous attempt failed) */}
      {findings.length > 0 && !analysis && !analyzing && (
        <div className="mt-3">
          <ActionDrawer
            label="Analyze"
            icon={<Sparkles size={13} />}
            color="#f59e0b"
            disabled={analyzing}
            loading={analyzing}
            loadingLabel="Analyzing..."
            placeholder="Focus analysis on... (e.g., 'IT outsourcing needs in manufacturing')"
            onRun={(context) => handleAnalyze(context)}
          >
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
              {['comprehensive', 'entity_extraction', 'competitive', 'risk_assessment'].map(t => (
                <button key={t}
                  style={{
                    fontSize: 9, padding: '2px 8px', borderRadius: 10,
                    background: 'var(--panel)', border: '1px solid var(--border)',
                    color: 'var(--muted)', cursor: 'pointer',
                  }}
                >
                  {t.replace('_', ' ')}
                </button>
              ))}
            </div>
          </ActionDrawer>
        </div>
      )}

      {/* Analysis output */}
      {analysis && <AnalysisPanel analysis={analysis} />}

      {/* Action buttons — shown AFTER analysis */}
      {status === 'succeeded' && analysis && (
        <div className="mt-3 flex flex-col gap-2"
          style={{ background: 'var(--panel2)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}
        >
          <div className="text-[10px] font-semibold tracking-widest" style={{ color: 'var(--muted)' }}>
            NEXT STEPS
          </div>
          <div className="flex gap-2 flex-wrap">
            {/* Go Deeper — fed by analysis research gaps + enrichment targets */}
            <ActionDrawer
              label="Go Deeper"
              icon={<ArrowDownToLine size={13} />}
              color="#a78bfa"
              disabled={goingDeeper}
              loading={goingDeeper}
              loadingLabel="Going deeper..."
              placeholder="What to investigate deeper... (e.g., 'Focus on CEO contacts only')"
              onRun={(context) => {
                const leads: string[] = []
                for (const gap of (analysis?.research_gaps ?? [])) {
                  leads.push(`${gap.entity}: ${gap.missing}`)
                }
                for (const target of (analysis?.enrichment_targets ?? [])) {
                  leads.push(`Enrich ${target.entity}: ${target.reason}`)
                }
                if (leads.length === 0 && trail.deeper_leads) {
                  leads.push(...trail.deeper_leads)
                }
                if (context) {
                  leads.unshift(`USER FOCUS: ${context}`)
                }
                if (leads.length === 0) {
                  leads.push('Expand research based on analysis')
                }
                onGoDeeper(leads)
              }}
            >
              {(analysis?.research_gaps?.length > 0 || analysis?.enrichment_targets?.length > 0) && (
                <div style={{ marginTop: 6 }}>
                  <span style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 600 }}>Will investigate:</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
                    {(analysis.research_gaps ?? []).slice(0, 3).map((gap: any, i: number) => (
                      <span key={i} style={{ fontSize: 9, color: '#a78bfa' }}>• {gap.entity}: {gap.missing}</span>
                    ))}
                    {(analysis.enrichment_targets ?? []).slice(0, 3).map((t: any, i: number) => (
                      <span key={i} style={{ fontSize: 9, color: '#60a5fa' }}>• {t.entity}: {t.reason}</span>
                    ))}
                  </div>
                </div>
              )}
            </ActionDrawer>

            {/* Re-Analyze */}
            <ActionDrawer
              label="Re-Analyze"
              icon={<RefreshCw size={13} />}
              color="#f59e0b"
              disabled={analyzing}
              loading={analyzing}
              loadingLabel="Analyzing..."
              placeholder="Focus analysis on... (e.g., 'IT outsourcing needs in manufacturing')"
              onRun={(context) => handleAnalyze(context)}
            >
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {['comprehensive', 'entity_extraction', 'competitive', 'risk_assessment'].map(t => (
                  <button key={t}
                    style={{
                      fontSize: 9, padding: '2px 8px', borderRadius: 10,
                      background: 'var(--panel)', border: '1px solid var(--border)',
                      color: 'var(--muted)', cursor: 'pointer',
                    }}
                  >
                    {t.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </ActionDrawer>

            {/* Save Pipeline */}
            {hasPipeline && (
              <button
                onClick={handleSavePipeline}
                disabled={savingPipeline || pipelineSaved}
                style={{
                  background: pipelineSaved ? '#4ade8022' : '#60a5fa22',
                  border: `1px solid ${pipelineSaved ? '#4ade8055' : '#60a5fa55'}`,
                  color: pipelineSaved ? '#4ade80' : '#60a5fa',
                  fontSize: 11, fontWeight: 600, padding: '6px 14px', borderRadius: 6,
                  cursor: savingPipeline || pipelineSaved ? 'not-allowed' : 'pointer',
                  opacity: savingPipeline ? 0.5 : 1,
                }}
              >
                {pipelineSaved
                  ? <><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Save size={12} /> Saved</span></>
                  : savingPipeline
                    ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Saving...</>
                    : <><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Save size={12} /> Save Pipeline</span></>}
              </button>
            )}

            {/* Export dropdown */}
            {runId && (
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setExportOpen(prev => !prev)}
                  disabled={exporting}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    background: '#34d39922', border: '1px solid #34d39955', color: '#34d399',
                    fontSize: 11, fontWeight: 600, padding: '6px 14px', borderRadius: 6,
                    cursor: exporting ? 'not-allowed' : 'pointer',
                    opacity: exporting ? 0.5 : 1,
                  }}
                >
                  {exporting ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Download size={12} />}
                  Export
                </button>
                {exportOpen && (
                  <div
                    style={{
                      position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 50,
                      background: 'var(--panel2)', border: '1px solid var(--border)', borderRadius: 6,
                      minWidth: 140, boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                    }}
                  >
                    {(['pdf', 'csv', 'xlsx'] as const).map(fmt => (
                      <button
                        key={fmt}
                        onClick={() => handleExport(fmt)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                          background: 'none', border: 'none', cursor: 'pointer',
                          fontSize: 11, color: 'var(--text)', padding: '8px 12px', textAlign: 'left',
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--panel)' }}
                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
                      >
                        {fmt === 'pdf' ? <FileText size={12} /> : <FileSpreadsheet size={12} />}
                        {fmt.toUpperCase()}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pre-analysis: show Go Deeper + Save Pipeline if no analysis yet */}
      {!analysis && (canGoDeeper || hasPipeline) && (
        <div className="mt-2 flex gap-2">
          {canGoDeeper && (
            <button
              onClick={() => onGoDeeper(
                (trail.deeper_leads ?? []).length > 0
                  ? trail.deeper_leads!
                  : findings.slice(0, 5).map((f: any) => f.title ?? f.content?.slice(0, 80) ?? 'Expand research')
              )}
              disabled={goingDeeper}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: '#a78bfa18', border: '1px solid #a78bfa44', color: '#a78bfa',
                fontSize: 11, fontWeight: 600, padding: '7px 14px', borderRadius: 8,
                cursor: goingDeeper ? 'not-allowed' : 'pointer',
                opacity: goingDeeper ? 0.5 : 1,
              }}
            >
              {goingDeeper
                ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Going deeper...</>
                : <><ArrowDownToLine size={12} /> Go Deeper</>}
            </button>
          )}
          {hasPipeline && (
            <button
              onClick={handleSavePipeline}
              disabled={savingPipeline || pipelineSaved}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: pipelineSaved ? '#4ade8018' : '#60a5fa18',
                border: `1px solid ${pipelineSaved ? '#4ade8044' : '#60a5fa44'}`,
                color: pipelineSaved ? '#4ade80' : '#60a5fa',
                fontSize: 11, fontWeight: 600, padding: '7px 14px', borderRadius: 8,
                cursor: savingPipeline || pipelineSaved ? 'not-allowed' : 'pointer',
                opacity: savingPipeline ? 0.5 : 1,
              }}
            >
              {pipelineSaved
                ? <><Save size={12} /> Saved</>
                : <><Save size={12} /> Save Pipeline</>}
            </button>
          )}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Session Stage Bar — horizontal pipeline stages for session runs
// ---------------------------------------------------------------------------

function SessionStageBar({ runIds, activeJobId }: { runIds: string[]; activeJobId: string | null }) {
  const runQueries = useQueries({
    queries: runIds.map(id => ({
      queryKey: ['pipeline-run', id],
      queryFn: () => getPipelineRun(id),
      refetchInterval: (q: any) => {
        const s = q.state.data?.status
        return s === 'running' || s === 'queued' ? 2000 : false
      },
    })),
  })

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 0,
      overflowX: 'auto', scrollbarWidth: 'none',
      height: 32, paddingLeft: 8, paddingRight: 8,
      background: 'var(--panel2)', borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {runIds.map((id, index) => {
        const run = runQueries[index]?.data
        const status = run?.status ?? 'queued'
        const labelFull = run?.research?.pir_answered ?? `run${index + 1}`
        const label = labelFull.length > 28 ? labelFull.slice(0, 28) + '…' : labelFull
        const isActive = id === activeJobId

        const dotColor = status === 'running' ? '#facc15'
          : status === 'succeeded' ? '#4ade80'
          : status === 'failed' ? '#ef4444'
          : '#475569'

        return (
          <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 0, flexShrink: 0 }}>
            <div
              title={`Run ${index + 1}: ${status}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                fontSize: 9, color: isActive ? 'var(--accent)' : 'var(--muted)',
                padding: '0 6px', whiteSpace: 'nowrap',
                animation: isActive && status === 'running' ? 'pulse 1.5s ease-in-out infinite' : undefined,
              }}
            >
              <span style={{
                fontSize: 7, color: dotColor,
                animation: isActive && status === 'running' ? 'pulse 1.5s ease-in-out infinite' : undefined,
              }}>
                {index === 0 ? '◆' : '◎'}
              </span>
              <span style={{ fontWeight: 600 }}>{index + 1}</span>
              <span title={labelFull} style={{ color: 'var(--muted)', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                · {label}
              </span>
            </div>
            {index < runIds.length - 1 && (
              <span style={{ fontSize: 9, color: 'var(--muted)', flexShrink: 0 }}>─→</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Session Canvas — merged findings across all session runs
// ---------------------------------------------------------------------------

const SC_COLORS: Record<string, string> = {
  live_search:        '#4ade80',
  prior_research:     '#60a5fa',
  primary_official:   '#a78bfa',
  primary_self:       '#facc15',
  training_generated: '#f87171',
}

type FindingWithMeta = ResearchFinding & { runIndex: number; runId: string }

const REJECTION_WORDS = /none of (the|these)|not (the one|what i|right|correct|it)|wrong (answer|result)|not (what|the one) i/i

function SessionCanvas({ runIds }: { runIds: string[] }) {
  const activeJobId = useSessionStore(s => s.activeJobId)
  const messages = useChatStore(s => s.messages)
  const sessionRunIds = useChatStore(s => s.sessionRunIds)

  // Build the set of run IDs that the user explicitly rejected via a follow-up message.
  const rejectedRunIds = useMemo(() => {
    const rejected = new Set<string>()
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i]
      if (m.role === 'user' && REJECTION_WORDS.test(m.content)) {
        // Find the most recent run that was added before message index i.
        // messages[j].id matches sessionRunIds entries when the run was pushed.
        const priorRunId = sessionRunIds
          .slice()
          .reverse()
          .find(rid => messages.slice(0, i).some(pm => pm.id === rid))
        if (priorRunId) {
          rejected.add(priorRunId)
        }
      }
    }
    return rejected
  }, [messages, sessionRunIds])

  const runQueries = useQueries({
    queries: runIds.map(id => ({
      queryKey: ['pipeline-run', id],
      queryFn: () => getPipelineRun(id),
      refetchInterval: (q: any) => {
        const s = q.state.data?.status
        return s === 'running' || s === 'queued' ? 2000 : false
      },
    })),
  })

  // Merge findings across all completed runs
  const allFindings: FindingWithMeta[] = []
  for (let i = 0; i < runIds.length; i++) {
    const run = runQueries[i]?.data
    if (run?.research?.findings) {
      for (const f of run.research.findings) {
        allFindings.push({ ...f, runIndex: i, runId: runIds[i] })
      }
    }
  }

  // Group by branch
  const byBranch: Record<string, FindingWithMeta[]> = {}
  for (const f of allFindings) {
    const branch = f.branch || 'general'
    ;(byBranch[branch] ??= []).push(f)
  }

  // Sort branches: branches with findings from latest run first
  const latestRunIndex = runIds.length - 1
  const sortedBranches = Object.keys(byBranch).sort((a, b) => {
    const aHasLatest = byBranch[a].some(f => f.runIndex === latestRunIndex) ? 1 : 0
    const bHasLatest = byBranch[b].some(f => f.runIndex === latestRunIndex) ? 1 : 0
    return bHasLatest - aHasLatest
  })

  // Latest completed run's pir_answered
  let latestPirAnswered: string | undefined
  for (let i = runIds.length - 1; i >= 0; i--) {
    const run = runQueries[i]?.data
    if (run?.status === 'succeeded' && run.research?.pir_answered) {
      latestPirAnswered = run.research.pir_answered
      break
    }
  }

  const hasAnyFindings = allFindings.length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Stage bar */}
      <SessionStageBar runIds={runIds} activeJobId={activeJobId} />

      {/* Summary strip */}
      {latestPirAnswered && (
        <div style={{
          padding: '4px 10px', fontSize: 10,
          background: '#a78bfa11', borderBottom: '1px solid #a78bfa22',
          color: '#a78bfa', flexShrink: 0,
        }}>
          <span style={{ fontWeight: 700, marginRight: 4 }}>◎ Latest:</span>
          <span>"{latestPirAnswered}"</span>
        </div>
      )}

      {/* Findings by branch cluster */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 10 }}>
        {!hasAnyFindings && (
          <p style={{ color: 'var(--muted)', fontSize: 11, textAlign: 'center', marginTop: 32 }}>
            Investigation in progress…
          </p>
        )}

        {sortedBranches.map(branch => {
          const findings = byBranch[branch]
          // Which run indices contributed to this branch
          const contributingRuns = [...new Set(findings.map(f => f.runIndex))].sort()
          const isLatestBranch = findings.some(f => f.runIndex === latestRunIndex)
          const allRejected = findings.every(f => rejectedRunIds.has(f.runId || ''))

          return (
            <div key={branch} style={{ marginBottom: 14, opacity: allRejected ? 0.5 : 1 }}>
              {/* Branch header */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 6, flexWrap: 'wrap',
              }}>
                <span style={{ fontSize: 8, color: isLatestBranch ? '#a78bfa' : 'var(--muted)' }}>
                  {isLatestBranch ? '●' : '◎'}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 700,
                  color: isLatestBranch ? 'var(--subtext)' : 'var(--muted)',
                  textDecoration: allRejected ? 'line-through' : 'none',
                }}>
                  {branch.replace(/_/g, ' ')}
                </span>
                {contributingRuns.map(ri => (
                  <span key={ri} style={{
                    fontSize: 8, padding: '1px 5px', borderRadius: 3, fontWeight: 600,
                    background: '#60a5fa18', color: '#60a5fa', border: '1px solid #60a5fa33',
                  }}>
                    Run {ri + 1}
                  </span>
                ))}
                <span style={{ fontSize: 9, color: 'var(--muted)', marginLeft: 'auto' }}>
                  {findings.length} finding{findings.length !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Finding cards */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {findings.map((f, fi) => {
                  const conf = f.confidence ?? 0
                  const level = conf >= 75 ? 'high' : conf >= 50 ? 'medium' : 'low'
                  const confColor = CONFIDENCE_COLORS[level]
                  const isError = (f as any).error_flagged === true || (f as any).finding_type === 'error'
                  const isRejected = f.runId ? rejectedRunIds.has(f.runId) : false

                  return (
                    <div
                      key={`${f.runId}-${fi}`}
                      style={{
                        background: 'var(--panel2)',
                        border: `1px solid ${isError ? '#f8717133' : 'var(--border)'}`,
                        borderLeft: isRejected ? '2px solid #f8717144' : isError ? '3px solid #f87171' : undefined,
                        borderRadius: 6, padding: '8px 10px', fontSize: 11,
                        opacity: isRejected ? 0.4 : 1,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: isError ? '#f87171' : confColor }}>
                          {isError ? 'error' : `${conf}%`}
                        </span>
                        <span style={{ color: 'var(--subtext)', fontWeight: 600, flex: 1, textDecoration: isRejected ? 'line-through' : 'none' }}>
                          {f.title ?? 'Finding'}
                        </span>
                        {isRejected && (
                          <span style={{ fontSize: 8, color: '#f87171', fontWeight: 700 }}>E5</span>
                        )}
                        <span style={{
                          fontSize: 8, padding: '1px 4px', borderRadius: 3, fontWeight: 600,
                          background: '#60a5fa18', color: '#60a5fa88',
                        }}>
                          R{f.runIndex + 1}
                        </span>
                      </div>
                      {f.content && (
                        <p style={{ color: 'var(--text)', fontSize: 10, lineHeight: 1.5, margin: 0, opacity: isError ? 0.5 : 1 }}>
                          {f.content}
                        </p>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, fontSize: 9, color: 'var(--muted)' }}>
                        {f.source && <span>{f.source}</span>}
                        {f.source_class && (() => {
                          const c = SC_COLORS[f.source_class] ?? '#94a3b8'
                          return (
                            <span style={{
                              fontSize: 8, padding: '1px 4px', borderRadius: 3,
                              background: `${c}26`, color: c, fontWeight: 600,
                            }}>
                              {f.source_class.replace(/_/g, ' ')}
                            </span>
                          )
                        })()}
                        {f.url && (
                          <a
                            href={f.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: '#60a5fa', textDecoration: 'none' }}
                          >
                            link
                          </a>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PipelineTabContent() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const col1Content = useSessionStore(s => s.col1Content)
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const [runError, setRunError] = useState<{ id: string; message: string } | null>(null)
  const [lockedIds, setLockedIds] = useState<Set<string>>(() => {
    try {
      const stored = window.localStorage?.getItem('locked_pipelines')
      return stored ? new Set(JSON.parse(stored)) : new Set()
    } catch { return new Set() }
  })

  const toggleLock = useCallback((id: string) => {
    setLockedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      try { window.localStorage?.setItem('locked_pipelines', JSON.stringify([...next])) } catch {}
      return next
    })
  }, [])

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })
  const { data: allRuns = [] } = useQuery({
    queryKey: ['pipeline-runs-all'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 5000,
  })

  const startRun = useMutation({
    mutationFn: (id: string) => startPipelineRun(id),
    onSuccess: () => {
      setRunError(null)
      qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] })
    },
    onError: (err: unknown, pipelineId: string) => {
      const axios = err as { response?: { data?: { detail?: string }; status?: number } }
      const detail = axios.response?.data?.detail
        || (err instanceof Error ? err.message : 'Failed to run pipeline')
      setRunError({ id: pipelineId, message: detail })
    },
  })
  const pauseRun = useMutation({
    mutationFn: cancelPipelineRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] }),
  })
  const deleteMut = useMutation({
    mutationFn: deletePipeline,
    onSuccess: () => {
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
        const latestRun = allRuns.find(r => r.pipeline_id === pipeline.id)
        const isSelected = runId && allRuns.find(r => r.id === runId && r.pipeline_id === pipeline.id)
        const isLocked = pipeline.is_system || lockedIds.has(pipeline.id)
        const hasIS = allRuns.some(r => r.pipeline_id === pipeline.id && r.trigger_type === 'agent_is')

        const handleNameClick = () => {
          if (latestRun) {
            setCol1Content({ type: 'pipeline_run', runId: latestRun.id })
          }
          // No navigate() fallback — edit button handles navigation
        }

        const rowContent = (
          <div
            data-testid={`pipeline-row-${pipeline.id}`}
            className="flex items-center px-3 py-2 rounded"
            style={{
              background: isSelected ? 'var(--panel2)' : 'var(--panel)',
              border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
              gap: 8,
            }}
          >
            {/* Action buttons — leftmost for thumb access */}
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              {activeRun ? (
                <button
                  title="Pause (cancel run)"
                  onClick={(e) => { e.stopPropagation(); pauseRun.mutate(activeRun.id) }}
                  disabled={pauseRun.isPending}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#facc15' }}
                >
                  ⏸
                </button>
              ) : (
                <button
                  title="Run pipeline"
                  onClick={(e) => { e.stopPropagation(); startRun.mutate(pipeline.id) }}
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
            </div>
            {/* Pipeline name — click to show latest run results */}
            <span
              className="text-xs font-medium truncate"
              style={{ color: 'var(--text)', cursor: 'pointer', flex: 1 }}
              onClick={handleNameClick}
            >
              {pipeline.name}
            </span>
            {/* IS badge */}
            {hasIS && (
              <span
                style={{
                  fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                  background: '#7c3aed22', color: '#a78bfa', border: '1px solid #7c3aed44',
                  flexShrink: 0,
                }}
              >
                IS
              </span>
            )}
            {/* Edit pipeline button */}
            <button
              title="Edit pipeline"
              onClick={(e) => { e.stopPropagation(); navigate(`/pipelines/${pipeline.id}`) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}
            >
              ✎
            </button>
            {/* Lock toggle */}
            <button
              title={isLocked ? 'Unlock pipeline' : 'Lock pipeline'}
              onClick={() => { if (!pipeline.is_system) toggleLock(pipeline.id) }}
              style={{
                background: 'none', border: 'none', cursor: pipeline.is_system ? 'default' : 'pointer',
                fontSize: 12, color: isLocked ? '#facc15' : 'var(--muted)', flexShrink: 0,
                opacity: pipeline.is_system ? 0.6 : 1,
              }}
            >
              {isLocked ? '🔒' : '🔓'}
            </button>
          </div>
        )

        const error = runError?.id === pipeline.id ? runError.message : null

        return (
          <div key={pipeline.id} className="mb-2">
            {isLocked ? rowContent : (
              <SwipeToDelete onDelete={() => deleteMut.mutate(pipeline.id)}>
                {rowContent}
              </SwipeToDelete>
            )}
            {error && (
              <div
                className="px-3 py-1.5 text-[10px] rounded-b"
                style={{
                  background: '#ef444415', color: '#f87171',
                  border: '1px solid #ef444433', borderTop: 'none', marginTop: -2,
                }}
                onClick={() => setRunError(null)}
                title="Click to dismiss"
              >
                {error}
              </div>
            )}
          </div>
        )
      })}

      {/* Always show create button */}
      <button
        onClick={() => navigate('/pipelines')}
        style={{
          width: '100%',
          padding: '8px 0',
          fontSize: 11,
          fontWeight: 600,
          borderRadius: 6,
          background: 'transparent',
          color: 'var(--accent)',
          border: '1px dashed var(--border)',
          cursor: 'pointer',
          marginTop: 4,
        }}
      >
        + Create Pipeline
      </button>
    </div>
  )
}

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('Pipeline')
  const [dismissedTabs, setDismissedTabs] = useState<Set<string>>(new Set())
  const tabBarRef = useRef<HTMLDivElement>(null)
  const col1Content = useSessionStore(s => s.col1Content)
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const sessionRunIds = useChatStore(s => s.sessionRunIds)

  const { data: runs = [] } = useQuery({
    queryKey: ['all-pipeline-runs'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 5000,
  })

  // Follow-up runs (everything after the genesis) should not get their own tab —
  // they belong to the same session and display within the genesis run's tab.
  const sessionFollowUpIds = new Set(sessionRunIds.slice(1))

  // Keep the most recent runs as dynamic tabs (running first, then latest completed)
  // Dismissed tabs are excluded unless they become active again (e.g. clicked from Live panel)
  // When a session is active, only show runs from that session (session isolation)
  const sessionRunIdSet = new Set(sessionRunIds)
  const runTabs = runs
    .filter(r => !dismissedTabs.has(r.id))
    .filter(r => !sessionFollowUpIds.has(r.id))
    .filter(r => sessionRunIds.length === 0 || sessionRunIdSet.has(r.id))
    .sort((a, b) => {
      // confirm_pending sorts like running (active, needs attention)
      const aActive = a.status === 'running' || a.status === 'confirm_pending'
      const bActive = b.status === 'running' || b.status === 'confirm_pending'
      if (aActive && !bActive) return -1
      if (bActive && !aActive) return 1
      if (a.status === 'running' && b.status !== 'running') return -1
      if (b.status === 'running' && a.status !== 'running') return 1
      return new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    })
    .slice(0, 8)

  // Auto-switch to run tab when a pipeline run or job is selected from LiveStream.
  // Also un-dismiss the tab if it was previously closed.
  useEffect(() => {
    if (col1Content?.type === 'pipeline_run') {
      setDismissedTabs(prev => { const n = new Set(prev); n.delete(col1Content.runId); return n })
      setActiveTab(`run:${col1Content.runId}`)
    } else if (col1Content?.type === 'job') {
      setDismissedTabs(prev => { const n = new Set(prev); n.delete(col1Content.jobId); return n })
      setActiveTab(`run:${col1Content.jobId}`)
    }
  }, [col1Content])

  const activeRunId = activeTab.startsWith('run:') ? activeTab.slice(4) : null

  // If the active run ID isn't in runTabs yet (e.g. freshly created from a Live panel click
  // before the next 5 s refetch), synthesise a placeholder tab so the button appears.
  const tabsToRender = activeRunId && !runTabs.find(r => r.id === activeRunId)
    ? [...runTabs, { id: activeRunId, pipeline_name: 'Run', status: 'queued', started_at: new Date().toISOString() }]
    : runTabs

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar with scroll arrows */}
      <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
        {/* Scroll left */}
        <button
          onClick={() => tabBarRef.current?.scrollBy({ left: -120, behavior: 'smooth' })}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 10, color: 'var(--muted)', padding: '4px 2px', flexShrink: 0,
          }}
          title="Scroll tabs left"
        >
          ◂
        </button>

        {/* Scrollable tab area */}
        <div
          ref={tabBarRef}
          className="flex items-center gap-1 py-1"
          style={{ flex: 1, overflowX: 'auto', scrollbarWidth: 'none' }}
        >
          {/* Pipeline tab (static, no close button) */}
          <button
            onClick={() => setActiveTab('Pipeline')}
            className="px-2 py-1 rounded text-[11px] font-medium transition-colors flex-shrink-0"
            style={{
              background: activeTab === 'Pipeline' ? 'var(--panel2)' : 'transparent',
              color:      activeTab === 'Pipeline' ? 'var(--accent)' : 'var(--muted)',
              border:     activeTab === 'Pipeline' ? '1px solid var(--border)' : '1px solid transparent',
              cursor: 'pointer',
            }}
          >
            Pipeline
          </button>

          {/* Dynamic run tabs with close button */}
          {tabsToRender.map(run => {
            const tabId: Tab = `run:${run.id}`
            const isActive = activeTab === tabId
            const statusDot = run.status === 'running' ? '#facc15' : run.status === 'succeeded' ? '#4ade80' : run.status === 'failed' ? '#ef4444' : run.status === 'confirm_pending' ? '#f59e0b' : '#475569'
            return (
              <div
                key={run.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0,
                  background: isActive ? 'var(--panel2)' : 'transparent',
                  border: isActive ? '1px solid var(--border)' : '1px solid transparent',
                  borderRadius: 6, paddingLeft: 8, paddingRight: 2,
                  maxWidth: 150,
                }}
              >
                <button
                  onClick={() => {
                    setActiveTab(tabId)
                    setCol1Content({ type: 'pipeline_run', runId: run.id })
                  }}
                  className="text-[10px] font-medium flex-shrink-0"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
                    color: isActive ? 'var(--accent)' : 'var(--muted)',
                    display: 'flex', alignItems: 'center', gap: 4,
                    overflow: 'hidden',
                  }}
                  title={`${run.pipeline_name} — ${run.status}`}
                >
                  <span style={{ fontSize: 6, color: statusDot }}>●</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.pipeline_name?.slice(0, 14) ?? 'Run'}
                  </span>
                  {run.id === sessionRunIds[0] && sessionRunIds.length > 1 && (
                    <span style={{
                      fontSize: 8, background: 'var(--accent)', color: 'var(--bg)',
                      borderRadius: 8, padding: '0 4px', marginLeft: 3, flexShrink: 0,
                    }}>
                      {sessionRunIds.length}
                    </span>
                  )}
                </button>
                {/* Close tab */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setDismissedTabs(prev => new Set(prev).add(run.id))
                    if (isActive) setActiveTab('Pipeline')
                  }}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    fontSize: 9, color: 'var(--muted)', padding: '2px 4px',
                    lineHeight: 1, borderRadius: 3,
                  }}
                  title="Close tab"
                  onMouseEnter={e => { e.currentTarget.style.color = '#ef4444' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--muted)' }}
                >
                  ×
                </button>
              </div>
            )
          })}
        </div>

        {/* Scroll right */}
        <button
          onClick={() => tabBarRef.current?.scrollBy({ left: 120, behavior: 'smooth' })}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 10, color: 'var(--muted)', padding: '4px 2px', flexShrink: 0,
          }}
          title="Scroll tabs right"
        >
          ▸
        </button>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'Pipeline' && <PipelineTabContent />}

        {activeRunId && (
          <div key={activeRunId} style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
            {sessionRunIds.length > 1 && sessionRunIds[0] === activeRunId ? (
              // Session mode: show unified canvas across all session runs
              <SessionCanvas runIds={sessionRunIds} />
            ) : (
              // Single run: existing behavior
              <PipelineRunResults
                runId={activeRunId}
                onNavigateRun={(newRunId) => setActiveTab(`run:${newRunId}`)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
