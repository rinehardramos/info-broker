import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { InlineError } from '@/components/ui/inline-error'
import { useDebouncedLoading } from '@/hooks/useDebouncedLoading'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { StatusBadge } from './StatusBadge'
import { DownloadMenu } from './DownloadMenu'
import { api } from '@/api/client'
import {
  getWorkingMemorySnapshots, type WorkingMemorySnapshot,
  getHypothesisXrefs, getContinueThread, upsertAnnotation, listAnnotations,
  type HypothesisXrefs, type FindingAnnotation,
} from '@/api/v3'
import { useNavigate } from 'react-router-dom'

interface RunDetail {
  id: string
  status: string
  query: string
  pipeline_name: string
  trigger_type: string
  started_at: string
  finished_at: string | null
  error_message: string | null
  research?: {
    findings?: Array<{
      title?: string
      content?: string
      snippet?: string
      url?: string
      source?: string
      confidence?: number
    }>
    summary?: string
    query?: string
  } | null
}

async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const { data } = await api.get<RunDetail>(`/v3/pipelines/runs/${runId}`)
  return data
}

export function ResultDrawer() {
  const { isOpen, runId, close } = useResultDrawerStore()
  const [tab, setTab] = useState('findings')

  useEffect(() => { if (!isOpen) setTab('findings') }, [isOpen])

  const {
    data: run,
    isLoading,
    isError: runError,
    error: runErrorObj,
    refetch: refetchRun,
  } = useQuery({
    queryKey: ['run-detail', runId],
    queryFn: () => fetchRunDetail(runId!),
    enabled: Boolean(isOpen && runId),
  })
  const showDrawerSkeleton = useDebouncedLoading(isLoading)

  // Path B: working-memory snapshots — only present when the run used the loop.
  // 404 is normal (single-shot runs have no snapshots) so swallow it quietly.
  const { data: wm } = useQuery({
    queryKey: ['run-working-memory', runId],
    queryFn: () => getWorkingMemorySnapshots(runId!).catch(() => null),
    enabled: Boolean(isOpen && runId),
    retry: false,
  })
  const turns = wm?.snapshots ?? []
  const hasLoopTurns = turns.length > 0
  const synthesisSummary = wm?.synthesis_summary ?? ''
  const decayInfo = wm?.decay
  const pirInfo = wm?.pir
  const costInfo = wm?.cost
  const navigate = useNavigate()

  // Absorption features (D/E/F) on this run
  const { data: xrefs } = useQuery<HypothesisXrefs>({
    queryKey: ['hypothesis-xrefs', runId],
    queryFn: () => getHypothesisXrefs(runId!),
    enabled: Boolean(isOpen && runId && hasLoopTurns),
    retry: false,
    staleTime: 5 * 60_000,
  })
  const { data: continueThread } = useQuery({
    queryKey: ['continue-thread', runId],
    queryFn: () => getContinueThread(runId!),
    enabled: Boolean(isOpen && runId && hasLoopTurns),
    retry: false,
    staleTime: 5 * 60_000,
  })
  const { data: annotations, refetch: refetchAnnotations } = useQuery<FindingAnnotation[]>({
    queryKey: ['annotations', runId],
    queryFn: () => listAnnotations(runId!),
    enabled: Boolean(isOpen && runId && hasLoopTurns),
    retry: false,
  })

  const findings = run?.research?.findings ?? []

  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) close() }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[680px] lg:max-w-[52vw] flex flex-col overflow-hidden p-0"
        style={{
          background: 'var(--panel)',
          borderLeft: '1px solid var(--border)',
          color: 'var(--text)',
        }}
      >
        {/* Header */}
        <SheetHeader className="px-5 pt-5 pb-3 flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
          <SheetTitle className="truncate text-sm font-semibold" style={{ color: 'var(--text)' }}>
            {showDrawerSkeleton ? (
              <Skeleton className="h-4 w-64" />
            ) : (
              run?.query ?? `Run ${runId?.slice(0, 8)}…`
            )}
          </SheetTitle>
          <SheetDescription className="flex items-center gap-2 mt-1">
            {run && <StatusBadge status={run.status} />}
            {run?.pipeline_name && (
              <Badge variant="outline" className="text-xs" style={{ borderColor: 'var(--border)', color: 'var(--subtext)' }}>
                {run.pipeline_name}
              </Badge>
            )}
            {run?.started_at && (
              <span className="text-xs" style={{ color: 'var(--muted)' }}>
                {new Date(run.started_at).toLocaleString()}
              </span>
            )}
          </SheetDescription>
        </SheetHeader>

        {/* Tabs */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <Tabs value={tab} onValueChange={setTab} className="flex flex-col h-full">
            <TabsList className="mx-5 mt-3 flex-shrink-0 self-start" style={{ background: 'var(--panel2)' }}>
              <TabsTrigger value="findings">
                Findings {findings.length > 0 && <span className="ml-1 opacity-60">({findings.length})</span>}
              </TabsTrigger>
              <TabsTrigger value="summary">Summary</TabsTrigger>
              {hasLoopTurns && (
                <TabsTrigger value="turns">
                  Turns <span className="ml-1 opacity-60">({turns.length})</span>
                </TabsTrigger>
              )}
              <TabsTrigger value="raw">Raw JSON</TabsTrigger>
            </TabsList>

            <TabsContent value="findings" className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
              {showDrawerSkeleton && (
                <>
                  <Skeleton className="h-[88px] w-full rounded-md" />
                  <Skeleton className="h-[88px] w-full rounded-md" />
                  <Skeleton className="h-[88px] w-full rounded-md" />
                </>
              )}
              {!showDrawerSkeleton && runError && (
                <InlineError
                  title="Couldn't load run"
                  message={(runErrorObj as Error | undefined)?.message}
                  onRetry={() => refetchRun()}
                />
              )}
              {!showDrawerSkeleton && !runError && findings.length === 0 && (
                run?.status === 'failed' ? (
                  <InlineError
                    title="Run failed"
                    message={run.error_message ?? 'Unknown error'}
                  />
                ) : (
                  <EmptyState
                    title="No findings yet"
                    hint="Findings will appear here as the brain produces them."
                  />
                )
              )}
              {findings.map((f, i) => (
                <div
                  key={i}
                  className="rounded-md p-3 text-xs"
                  style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
                >
                  {f.title && <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{f.title}</div>}
                  {(f.content ?? f.snippet) && (
                    <div className="mb-2 leading-relaxed" style={{ color: 'var(--subtext)' }}>
                      {(f.content ?? f.snippet)?.slice(0, 400)}
                      {((f.content ?? f.snippet)?.length ?? 0) > 400 && '…'}
                    </div>
                  )}
                  <div className="flex items-center gap-3 flex-wrap">
                    {f.source && (
                      <span style={{ color: 'var(--muted)' }}>{f.source}</span>
                    )}
                    {f.confidence !== undefined && (
                      <span style={{ color: 'var(--accent)' }}>{Math.round(f.confidence * 100)}% confidence</span>
                    )}
                    {f.url && (
                      <a
                        href={f.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline truncate max-w-xs"
                        style={{ color: 'var(--accent)' }}
                      >
                        {f.url}
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </TabsContent>

            <TabsContent value="summary" className="flex-1 overflow-y-auto px-5 py-3">
              {showDrawerSkeleton ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-11/12" />
                  <Skeleton className="h-4 w-10/12" />
                  <Skeleton className="h-4 w-9/12" />
                  <Skeleton className="h-4 w-8/12" />
                </div>
              ) : runError ? (
                <InlineError
                  title="Couldn't load run"
                  message={(runErrorObj as Error | undefined)?.message}
                  onRetry={() => refetchRun()}
                />
              ) : run?.research?.summary ? (
                <p className="text-sm leading-relaxed" style={{ color: 'var(--subtext)' }}>
                  {run.research.summary}
                </p>
              ) : (
                <EmptyState
                  title="No summary"
                  hint="The brain didn't produce a summary for this run."
                />
              )}
            </TabsContent>

            {hasLoopTurns && (
              <TabsContent value="turns" className="flex-1 overflow-y-auto px-5 py-3 space-y-2">
                <LoopBanner turns={turns} />
                {costInfo && costInfo.total_ru > 0 && (
                  <div
                    className="rounded-md p-2 text-[11px]"
                    style={{
                      background: 'var(--panel2)',
                      border: '1px solid var(--border)',
                      color: 'var(--subtext)',
                    }}
                    title="Per-phase RU consumption — explore (cheap discovery) vs test (verification) vs synthesize"
                  >
                    <div className="flex items-center justify-between">
                      <span>
                        <span className="opacity-60">Cost · </span>
                        <strong style={{ color: 'var(--text)' }}>{costInfo.total_ru} RU</strong>
                      </span>
                      <span className="flex gap-2 text-[10px]">
                        {Object.entries(costInfo.by_phase).map(([phase, ru]) => {
                          const color =
                            phase === 'explore'    ? '#67e8f9' :  // cyan
                            phase === 'test'       ? '#fbbf24' :  // amber
                            phase === 'synthesize' ? '#4ade80' :  // green
                                                     'var(--muted)'
                          return (
                            <span key={phase} style={{ color }}>
                              {phase} {ru}
                            </span>
                          )
                        })}
                      </span>
                    </div>
                  </div>
                )}
                {pirInfo && pirInfo.total_eeis > 0 && (
                  <div
                    className="rounded-md p-2 text-[11px]"
                    style={{
                      background: 'var(--panel2)',
                      border: '1px solid var(--border)',
                      color: 'var(--subtext)',
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full"
                        style={{
                          background:
                            pirInfo.overall_coverage >= 0.8 ? '#4ade80' :
                            pirInfo.overall_coverage >= 0.5 ? '#fbbf24' : '#ef4444',
                        }}
                      />
                      <span>
                        PIR coverage ({pirInfo.entity_type}):{' '}
                        <strong style={{ color: 'var(--text)' }}>
                          {pirInfo.resolved_eeis}/{pirInfo.total_eeis}
                        </strong>{' '}
                        EEIs resolved
                        {pirInfo.gaps.length > 0 && ` · ${pirInfo.gaps.length} gaps`}
                      </span>
                    </div>
                    {pirInfo.gaps.length > 0 && (
                      <div
                        className="mt-1 text-[10px] opacity-70"
                        title={pirInfo.gaps.join('\n')}
                      >
                        Missing: {pirInfo.gaps.slice(0, 3).join(' · ')}
                        {pirInfo.gaps.length > 3 && ` · +${pirInfo.gaps.length - 3} more`}
                      </div>
                    )}
                  </div>
                )}
                {decayInfo && decayInfo.decayed_prior_count > 0 && (
                  <div
                    className="rounded-md p-2 text-[11px] flex items-center gap-2"
                    style={{
                      background: 'var(--panel2)',
                      border: '1px solid #f59e0b40',
                      color: 'var(--subtext)',
                    }}
                    title="Cross-run priors that lost confidence due to age past shelf life"
                  >
                    <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: '#f59e0b' }} />
                    <span>
                      {decayInfo.decayed_prior_count} cross-run prior{decayInfo.decayed_prior_count === 1 ? '' : 's'} aged out
                      {decayInfo.max_decay_pct > 0 ? ` · up to −${decayInfo.max_decay_pct}% confidence` : ''}
                    </span>
                  </div>
                )}
                {synthesisSummary && (
                  <div
                    className="rounded-md p-3 text-xs leading-relaxed"
                    style={{
                      background: 'var(--panel2)',
                      border: '1px solid var(--border)',
                      color: 'var(--text)',
                    }}
                  >
                    <div className="text-[10px] uppercase tracking-wider mb-1.5"
                         style={{ color: 'var(--muted)' }}>
                      Synthesis (final turn)
                    </div>
                    <div className="whitespace-pre-wrap" style={{ color: 'var(--subtext)' }}>
                      {synthesisSummary}
                    </div>
                  </div>
                )}
                {continueThread?.suggested_query && (
                  <div
                    className="rounded-md p-2 text-[11px] flex items-center justify-between gap-2"
                    style={{
                      background: '#a78bfa10',
                      border: '1px solid #a78bfa40',
                      color: 'var(--subtext)',
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="opacity-60 text-[9px] uppercase tracking-wider mb-0.5">
                        Continue thread
                      </div>
                      <div className="truncate" title={continueThread.suggested_query}>
                        {continueThread.target_open_question || continueThread.suggested_query.slice(0, 100)}
                      </div>
                    </div>
                    <button
                      onClick={() => navigate(`/research?q=${encodeURIComponent(continueThread.suggested_query!)}`)}
                      className="text-[10px] px-2 py-1 rounded font-semibold flex-shrink-0"
                      style={{ background: '#a78bfa', color: '#1e1b4b', border: 'none' }}
                      data-testid="continue-thread-btn"
                    >
                      Investigate →
                    </button>
                  </div>
                )}
                {xrefs && xrefs.xrefs.some(x => x.related.length > 0) && (
                  <div
                    className="rounded-md p-2 text-[10px]"
                    style={{
                      background: 'var(--panel2)',
                      border: '1px solid var(--border)',
                      color: 'var(--subtext)',
                    }}
                  >
                    <div className="opacity-60 mb-1">
                      🔗 You've researched related hypotheses before:
                    </div>
                    {xrefs.xrefs.filter(x => x.related.length > 0).slice(0, 3).map((x) => (
                      <div key={x.hypothesis_id} className="mb-1">
                        <span className="opacity-70">{x.statement.slice(0, 70)}…</span>
                        <span className="opacity-50 ml-1">
                          ({x.related.length} prior hit{x.related.length === 1 ? '' : 's'}{x.related.some(r => r.user_graded) ? ', incl. graded A' : ''})
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {turns.length > 0 && <ACHMatrixGrid finalSnap={turns[turns.length - 1]} />}
                {turns.map((t) => <TurnRow key={t.turn} snap={t} />)}
                {hasLoopTurns && runId && (
                  <AnnotationPad
                    runId={runId}
                    annotations={annotations ?? []}
                    onSaved={() => refetchAnnotations()}
                  />
                )}
              </TabsContent>
            )}

            <TabsContent value="raw" className="flex-1 overflow-y-auto px-5 py-3">
              {showDrawerSkeleton ? (
                <div className="space-y-1.5">
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-2/3" />
                  <Skeleton className="h-3 w-4/5" />
                  <Skeleton className="h-3 w-3/5" />
                  <Skeleton className="h-3 w-2/4" />
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              ) : runError ? (
                <InlineError
                  title="Couldn't load run JSON"
                  message={(runErrorObj as Error | undefined)?.message}
                  onRetry={() => refetchRun()}
                />
              ) : (
                <pre className="text-xs whitespace-pre-wrap" style={{ color: 'var(--subtext)' }}>
                  {JSON.stringify(run ?? { runId }, null, 2)}
                </pre>
              )}
            </TabsContent>
          </Tabs>
        </div>

        {/* Footer */}
        <SheetFooter
          className="px-5 py-3 flex-shrink-0"
          style={{ borderTop: '1px solid var(--border)', background: 'var(--panel)' }}
        >
          {runId ? <DownloadMenu runId={runId} /> : null}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}


// ── source-class palette ─────────────────────────────────────────────────────
// Higher quality = greener; lower = greyer/amber. Matches OSINT hierarchy:
// primary > registry > news > aggregator > social > training > unknown.
const SOURCE_CLASS_PALETTE: Record<string, { bg: string; fg: string }> = {
  primary_official: { bg: '#16a34a20', fg: '#4ade80' },
  registry:         { bg: '#22c55e20', fg: '#86efac' },
  news:             { bg: '#06b6d420', fg: '#67e8f9' },
  aggregator:       { bg: '#f59e0b20', fg: '#fbbf24' },
  social:           { bg: '#a855f720', fg: '#c4b5fd' },
  training:         { bg: '#71717a20', fg: '#a1a1aa' },
  unknown:          { bg: '#52525b20', fg: '#71717a' },
}
function sourceClassBg(cls: string): string { return (SOURCE_CLASS_PALETTE[cls] ?? SOURCE_CLASS_PALETTE.unknown).bg }
function sourceClassFg(cls: string): string { return (SOURCE_CLASS_PALETTE[cls] ?? SOURCE_CLASS_PALETTE.unknown).fg }


function LoopBanner({ turns }: { turns: WorkingMemorySnapshot[] }) {
  const final = turns[turns.length - 1]
  const finalPhase = final?.phase
  const totalHs    = (final?.counts.hypotheses_open ?? 0) + (final?.counts.hypotheses_resolved ?? 0)
  const resolved   = final?.counts.hypotheses_resolved ?? 0
  const wm         = (final?.working_memory ?? {}) as Record<string, unknown>
  const contradictions = (wm.contradictions ?? []) as Array<{ status: string }>
  const openC      = contradictions.filter(c => c.status === 'open').length
  const totalC     = contradictions.length
  const isComplete = finalPhase === 'synthesize'
                     && (totalHs === 0 || resolved >= totalHs)
                     && openC === 0
  const colorVar   = isComplete ? '#4ade80' : openC > 0 ? '#ef4444' : '#fbbf24'
  const parts = [
    isComplete ? 'complete' : 'partial',
    `${resolved}/${totalHs || 0} hypotheses verified`,
    `${turns.length} turns`,
  ]
  if (totalC > 0) parts.splice(2, 0, `${totalC - openC}/${totalC} contradictions resolved`)
  if (!isComplete) parts.push(`final phase ${finalPhase}`)
  return (
    <div
      className="rounded-md p-2 text-[11px] flex items-center gap-2"
      style={{
        background: 'var(--panel2)',
        border: `1px solid ${colorVar}40`,
        color: 'var(--subtext)',
      }}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: colorVar }} />
      <span>{parts.join(' · ')}</span>
    </div>
  )
}


// ── D. Annotation pad — free-form notes on a finding ────────────────────────
function AnnotationPad({
  runId, annotations, onSaved,
}: { runId: string; annotations: FindingAnnotation[]; onSaved: () => void }) {
  const [findingId, setFindingId] = useState('')
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (!findingId || !body.trim()) return
    setSaving(true)
    try {
      await upsertAnnotation(runId, findingId.trim(), body.trim())
      setBody('')
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="rounded-md p-2 text-[11px] mt-2"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="opacity-60 text-[10px] uppercase tracking-wider mb-1">
        Analyst annotations
      </div>
      {annotations.length > 0 && (
        <ul className="space-y-1 mb-2">
          {annotations.slice(0, 8).map((a) => (
            <li key={a.id} className="flex items-baseline gap-2">
              <span
                className="text-[9px] px-1 py-px rounded"
                style={{
                  background: a.color === 'red' ? '#ef444430' : '#fde04830',
                  color: a.color === 'red' ? '#fca5a5' : '#fde047',
                }}
              >
                {a.finding_id.slice(0, 8)}
              </span>
              <span style={{ color: 'var(--text)' }}>{a.body}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-1">
        <input
          type="text"
          value={findingId}
          onChange={(e) => setFindingId(e.target.value)}
          placeholder="finding id"
          className="px-2 py-1 text-[10px] rounded outline-none"
          style={{ background: 'var(--panel)', color: 'var(--text)',
                   border: '1px solid var(--border)', width: 100 }}
        />
        <input
          type="text"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="note…"
          className="flex-1 px-2 py-1 text-[11px] rounded outline-none"
          style={{ background: 'var(--panel)', color: 'var(--text)',
                   border: '1px solid var(--border)' }}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
        />
        <button
          onClick={submit}
          disabled={saving || !findingId || !body.trim()}
          className="px-2 py-1 text-[10px] rounded disabled:opacity-50"
          style={{ background: 'var(--accent, #a78bfa)', color: '#1e1b4b', border: 'none' }}
        >
          {saving ? '…' : 'Save'}
        </button>
      </div>
    </div>
  )
}


// ── ACH matrix grid (findings × hypotheses, colored by consistency) ─────────
interface MatrixCell {
  finding_id: string
  hypothesis_id: string
  consistency: 'consistent' | 'inconsistent' | 'neutral' | 'not_applicable' | string
  note?: string
}
interface MatrixFinding { id: string; title: string }
interface MatrixHypothesis { id: string; statement: string; status: string }

const CELL_BG: Record<string, string> = {
  consistent:     '#16a34a',     // green
  inconsistent:   '#ef4444',     // red
  neutral:        '#71717a',     // gray
  not_applicable: '#3f3f4640',   // dim
}

function ACHMatrixGrid({ finalSnap }: { finalSnap: WorkingMemorySnapshot }) {
  const [expanded, setExpanded] = useState(false)
  const wm = (finalSnap.working_memory ?? {}) as Record<string, unknown>
  const matrix = (wm.evidence_matrix ?? []) as MatrixCell[]
  const findings = (wm.findings ?? []) as MatrixFinding[]
  const hypotheses = (wm.hypotheses ?? []) as MatrixHypothesis[]
  if (matrix.length === 0 || findings.length === 0 || hypotheses.length === 0) {
    return null
  }
  // Index for fast cell lookup
  const cellByPair: Record<string, MatrixCell> = {}
  for (const c of matrix) cellByPair[`${c.finding_id}|${c.hypothesis_id}`] = c

  // Only show findings that have at least one score (avoids a sea of empties).
  const scoredFindingIds = new Set(matrix.map(c => c.finding_id))
  const rows = findings.filter(f => scoredFindingIds.has(f.id))

  return (
    <div
      className="rounded-md p-3 text-[11px]"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)', color: 'var(--subtext)' }}
    >
      <div className="flex items-center justify-between">
        <div className="font-semibold" style={{ color: 'var(--text)' }}>
          ACH evidence matrix
          <span className="ml-2 opacity-60 font-normal">
            {rows.length} finding{rows.length === 1 ? '' : 's'} × {hypotheses.length} hypothesis · {matrix.length} scored
          </span>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          className="text-[10px] underline opacity-60 hover:opacity-100"
          style={{ color: 'var(--accent)' }}
        >
          {expanded ? 'Hide matrix' : 'Show matrix'}
        </button>
      </div>
      {expanded && (
        <div className="mt-3 overflow-x-auto">
          <table
            className="text-[10px] border-separate"
            style={{ borderSpacing: 2, tableLayout: 'fixed', width: '100%' }}
          >
            <thead>
              <tr>
                <th
                  className="text-left pr-2"
                  style={{ color: 'var(--muted)', width: '60%' }}
                >
                  finding
                </th>
                {hypotheses.map((h, i) => (
                  <th
                    key={h.id}
                    style={{ color: 'var(--muted)', width: 28, textAlign: 'center' }}
                    title={`${h.statement} [${h.status}]`}
                  >
                    H{i + 1}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr key={f.id}>
                  <td
                    className="pr-2"
                    style={{
                      color: 'var(--subtext)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      maxWidth: 0,        // forces table-layout: fixed truncation
                    }}
                    title={f.title}
                  >
                    {f.title}
                  </td>
                  {hypotheses.map((h) => {
                    const cell = cellByPair[`${f.id}|${h.id}`]
                    const bg = cell ? (CELL_BG[cell.consistency] ?? '#3f3f4660') : 'transparent'
                    const fg = cell?.consistency === 'inconsistent' || cell?.consistency === 'consistent' ? '#fff' : 'var(--muted)'
                    const glyph =
                      cell?.consistency === 'consistent'     ? '+' :
                      cell?.consistency === 'inconsistent'   ? '−' :
                      cell?.consistency === 'neutral'        ? '·' :
                      cell?.consistency === 'not_applicable' ? '/' : ''
                    return (
                      <td
                        key={h.id}
                        style={{
                          background: bg,
                          color: fg,
                          textAlign: 'center',
                          width: 24, height: 18,
                          borderRadius: 3,
                        }}
                        title={cell ? `${cell.consistency}${cell.note ? ': ' + cell.note : ''}` : 'unscored'}
                      >
                        {glyph}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-[9px] opacity-60 flex gap-3">
            <span><span style={{ background: CELL_BG.consistent, color: 'white', padding: '0 4px', borderRadius: 2 }}>+</span> consistent</span>
            <span><span style={{ background: CELL_BG.inconsistent, color: 'white', padding: '0 4px', borderRadius: 2 }}>−</span> inconsistent</span>
            <span><span style={{ background: CELL_BG.neutral, color: 'white', padding: '0 4px', borderRadius: 2 }}>·</span> neutral</span>
            <span><span style={{ background: CELL_BG.not_applicable, color: 'var(--muted)', padding: '0 4px', borderRadius: 2 }}>/</span> N/A</span>
          </div>
        </div>
      )}
    </div>
  )
}

function TurnRow({ snap }: { snap: WorkingMemorySnapshot }) {
  const [expanded, setExpanded] = useState(false)
  const phaseColor =
    snap.phase === 'explore'    ? 'text-sky-300'    :
    snap.phase === 'test'       ? 'text-amber-300'  :
    snap.phase === 'synthesize' ? 'text-green-300'  : 'text-zinc-300'
  return (
    <div
      className="rounded-md p-3 text-xs"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold" style={{ color: 'var(--text)' }}>
            Turn {snap.turn}
          </span>
          <span className={`text-[10px] uppercase tracking-wider ${phaseColor}`}>
            {snap.phase}
          </span>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          className="text-[10px] underline opacity-60 hover:opacity-100"
          style={{ color: 'var(--accent)' }}
        >
          {expanded ? 'Hide JSON' : 'Show JSON'}
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1" style={{ color: 'var(--muted)' }}>
        <span>hypotheses {snap.counts.hypotheses_open}/<span style={{ color: 'var(--subtext)' }}>{snap.counts.hypotheses_resolved} resolved</span></span>
        <span>facts {snap.counts.facts}</span>
        <span>findings {snap.counts.findings}</span>
        <span>open Qs {snap.counts.open_questions}</span>
        <span>strategies {snap.counts.strategies_tried}</span>
      </div>
      {snap.source_classes && Object.keys(snap.source_classes).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {Object.entries(snap.source_classes)
            .sort((a, b) => b[1] - a[1])
            .map(([cls, n]) => (
              <span
                key={cls}
                className="text-[9px] px-1.5 py-px rounded uppercase tracking-wider"
                style={{
                  background: sourceClassBg(cls),
                  color: sourceClassFg(cls),
                  border: `1px solid ${sourceClassFg(cls)}40`,
                }}
                title={`${cls} sources used this turn`}
              >
                {cls.replace('_', ' ')} {n}
              </span>
            ))}
        </div>
      )}
      {(snap.deception?.flagged_count ?? 0) > 0 && (
        <div className="mt-2 text-[10px] flex items-center gap-2"
             style={{ color: 'var(--muted)' }}>
          <span className="inline-block px-1.5 py-px rounded uppercase tracking-wider text-[9px]"
                style={{
                  background: '#ef444420',
                  color: '#fca5a5',
                  border: '1px solid #ef444440',
                }}
                title={'Deception flags: ' + Object.entries(snap.deception!.flag_counts).map(([k,v]) => `${k} ${v}`).join(', ')}>
            ⚠ {snap.deception!.flagged_count} flagged
          </span>
          <span className="opacity-70">
            {Object.entries(snap.deception!.flag_counts).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}
          </span>
        </div>
      )}
      {snap.ach_ranking && snap.ach_ranking.length > 0 && (snap.evidence_matrix_size ?? 0) > 0 && (
        <div className="mt-2 text-[10px]" style={{ color: 'var(--muted)' }}>
          <div className="opacity-60 mb-0.5">
            ACH ranking · {snap.evidence_matrix_size} scores ·
            fewest inconsistencies wins:
          </div>
          {snap.ach_ranking.slice(0, 4).map((row) => (
            <div key={row.hypothesis_id} className="flex items-center gap-2 truncate">
              <span style={{
                color: row.inconsistencies === 0 && row.consistencies > 0 ? '#4ade80' : 'var(--subtext)',
                minWidth: 60,
              }}>
                {row.inconsistencies}i / {row.consistencies}c
              </span>
              <span className="truncate" title={row.statement} style={{ color: 'var(--subtext)' }}>
                {row.statement.slice(0, 80)}
              </span>
            </div>
          ))}
        </div>
      )}
      {expanded && (
        <pre className="mt-2 text-[10px] whitespace-pre-wrap" style={{ color: 'var(--subtext)' }}>
          {JSON.stringify(snap.working_memory, null, 2)}
        </pre>
      )}
    </div>
  )
}
