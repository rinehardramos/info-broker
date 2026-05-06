import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { listPipelines, startPipelineRun, cancelPipelineRun, deletePipeline, listAllPipelineRuns, getPipelineRun, createPipeline, type ResearchTrail } from '../../api/pipelines'
import { sendMessage, runAnalyzer, submitFindingFeedback, getRunFeedback } from '../../api/v3'
import { ResearchFlow } from './ResearchFlow'
import { AnalysisPanel } from './AnalysisPanel'
import { ActionDrawer } from './ActionDrawer'
import { Sparkles, ArrowDownToLine, Save, ThumbsUp, ThumbsDown, RefreshCw, RotateCcw, Layers, Loader2 } from 'lucide-react'

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

    function begin(x: number) {
      startX = x; currentX = 0; swiped = false
      el.style.transition = ''
    }
    function move(x: number) {
      const dx = x - startX
      currentX = Math.min(0, dx)
      if (currentX < -SWIPE_DEAD_ZONE) swiped = true
      if (swiped) el.style.transform = `translateX(${currentX}px)`
    }
    function end() {
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
      return status === 'running' || status === 'queued' ? 3000 : false
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
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<any>(null)
  const [feedback, setFeedback] = useState<Record<number, number>>({})

  useEffect(() => {
    if (runId) {
      getRunFeedback(runId).then(fb => {
        const mapped: Record<number, number> = {}
        Object.entries(fb).forEach(([idx, val]) => { mapped[Number(idx)] = val.score })
        setFeedback(mapped)
      }).catch(() => {})
    }
  }, [runId])

  const handleAnalyze = async (context?: string) => {
    setAnalyzing(true)
    try {
      const result = await runAnalyzer(research.findings, undefined, context || undefined)
      // API returns {status, items: [...], count} — extract the analysis from items[0]
      const analysis = result?.items?.[0] ?? (Array.isArray(result) ? result[0] : result)
      setAnalysis(analysis)
    } catch (err) {
      console.error('Analysis failed:', err)
    } finally {
      setAnalyzing(false)
    }
  }

  const handleFeedback = async (index: number, score: number, title: string) => {
    setFeedback(prev => ({ ...prev, [index]: score }))
    if (runId) {
      await submitFindingFeedback(runId, index, score, undefined, title)
    }
  }
  const { findings, trail } = research
  const canGoDeeper = trail.can_go_deeper && (trail.deeper_leads?.length ?? 0) > 0
  const hasPipeline = research.suggested_pipeline != null && (research.suggested_pipeline.nodes?.length ?? 0) > 0

  async function handleSavePipeline() {
    if (!research.suggested_pipeline) return
    setSavingPipeline(true)
    try {
      const sp = research.suggested_pipeline
      // Generate IDs for nodes and map source_index/target_index to node IDs
      const nodeIds = sp.nodes.map(() => crypto.randomUUID())
      const result = await createPipeline({
        name: sp.name,
        description: `Generated from IS research: "${research.query}"`,
        nodes: sp.nodes.map((n, i) => ({
          id: nodeIds[i],
          node_type: n.node_type,
          label: n.label,
          config: n.config ?? {},
          position_y: i,
        })),
        edges: sp.edges.map(e => ({
          source_node_id: nodeIds[e.source_index],
          target_node_id: nodeIds[e.target_index],
        })),
      })
      setPipelineSaved(true)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      // Navigate to the new pipeline
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
                <p style={{ color: 'var(--muted)', fontSize: 10, lineHeight: 1.4, marginTop: 4, opacity: isError ? 0.6 : 1 }}>
                  {f.content.slice(0, 300)}{f.content.length > 300 ? '...' : ''}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2" style={{ fontSize: 9, color: 'var(--muted)', opacity: isError ? 0.6 : 1 }}>
                {f.source && <span>{f.source}</span>}
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
              <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                <button
                  onClick={() => handleFeedback(i, 1, f.title ?? '')}
                  style={{
                    background: feedback[i] === 1 ? '#4ade8033' : 'transparent',
                    border: `1px solid ${feedback[i] === 1 ? '#4ade80' : 'var(--border)'}`,
                    color: feedback[i] === 1 ? '#4ade80' : 'var(--muted)',
                    fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                  }}
                >
                  <ThumbsUp size={11} />
                </button>
                <button
                  onClick={() => handleFeedback(i, -1, f.title ?? '')}
                  style={{
                    background: feedback[i] === -1 ? '#f8717133' : 'transparent',
                    border: `1px solid ${feedback[i] === -1 ? '#f87171' : 'var(--border)'}`,
                    color: feedback[i] === -1 ? '#f87171' : 'var(--muted)',
                    fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                  }}
                >
                  <ThumbsDown size={11} />
                </button>
                {feedback[i] === -1 && (
                  <span style={{ fontSize: 9, color: '#f87171', alignSelf: 'center' }}>Marked irrelevant</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

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

      {/* Analyze button — shown before analysis is done */}
      {status === 'succeeded' && findings.length > 0 && !analysis && (
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
          </div>
        </div>
      )}

      {/* Pre-analysis: show original Go Deeper (skip) + Save Pipeline if no analysis yet */}
      {status === 'succeeded' && !analysis && (canGoDeeper || hasPipeline) && (
        <div className="mt-2 flex gap-2">
          {canGoDeeper && (
            <button
              onClick={() => onGoDeeper(trail.deeper_leads!)}
              disabled={goingDeeper}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)',
                fontSize: 10, padding: '5px 12px', borderRadius: 8,
                cursor: goingDeeper ? 'not-allowed' : 'pointer',
              }}
            >
              {goingDeeper
                ? <><Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> Going deeper...</>
                : <><ArrowDownToLine size={11} /> Go Deeper (skip analysis)</>}
            </button>
          )}
          {hasPipeline && (
            <button
              onClick={handleSavePipeline}
              disabled={savingPipeline || pipelineSaved}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)',
                fontSize: 10, padding: '5px 12px', borderRadius: 8,
                cursor: savingPipeline || pipelineSaved ? 'not-allowed' : 'pointer',
              }}
            >
              {pipelineSaved
                ? <><Save size={11} /> Saved</>
                : <><Save size={11} /> Save Pipeline</>}
            </button>
          )}
        </div>
      )}
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

  const { data: runs = [] } = useQuery({
    queryKey: ['all-pipeline-runs'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 5000,
  })

  // Keep the most recent runs as dynamic tabs (running first, then latest completed)
  // Dismissed tabs are excluded unless they become active again (e.g. clicked from Live panel)
  const runTabs = runs
    .filter(r => !dismissedTabs.has(r.id))
    .sort((a, b) => {
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
            const statusDot = run.status === 'running' ? '#facc15' : run.status === 'succeeded' ? '#4ade80' : run.status === 'failed' ? '#ef4444' : '#475569'
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
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <PipelineRunResults
              runId={activeRunId}
              onNavigateRun={(newRunId) => setActiveTab(`run:${newRunId}`)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
