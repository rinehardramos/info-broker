import React, { useCallback, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { StreamingCardList } from './StreamingCardList'
import { FlowMiniPreview } from './FlowMiniPreview'
import { PhaseDAGView } from './PhaseDAGView'
import { ShareDialog } from './ShareDialog'
import { SummaryModal } from './SummaryModal'
import { DownloadMenu } from '../runs/DownloadMenu'
import { getPipelineRun, createPipeline } from '../../api/pipelines'
import { useLayoutStore } from '@/stores/layoutStore'
import { useRunStreamStore } from '@/stores/runStreamStore'

interface RunResultsViewProps {
  runId: string
}

function DebugBadge({ runId }: { runId: string }) {
  const run = useRunStreamStore((s) => s.runsById[runId])
  const allIds = useRunStreamStore((s) => Object.keys(s.runsById))
  const [copied, setCopied] = useState(false)
  const copyRunId = useCallback(() => {
    navigator.clipboard?.writeText(runId).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 1500) },
      () => {},
    )
  }, [runId])
  return (
    <div className="px-2 py-1 text-[9px] font-mono border-b border-border bg-amber-500/5 text-amber-500/80 flex items-center gap-2 select-text">
      <button
        type="button"
        onClick={copyRunId}
        title="Click to copy full run id"
        className="hover:text-amber-300 transition-colors cursor-pointer"
      >
        run: <span className="text-amber-400 underline decoration-dotted">{runId.slice(0, 8)}</span>
        {copied ? <span className="ml-1 text-emerald-400">✓ copied</span> : <span className="ml-1 opacity-50">⧉</span>}
      </button>
      <span>·</span>
      <span title="Whether the runStreamStore has entries for this runId">
        store: <span className={run ? 'text-emerald-400' : 'text-red-400'}>
          {run ? `${run.kind}/${run.status} (${run.cardOrder.length} cards)` : 'MISS'}
        </span>
      </span>
      {!run && allIds.length > 0 && (
        <span title="Ids that ARE in the store" className="opacity-70">
          · have: {allIds.map(id => id.slice(0, 8)).join(', ')}
        </span>
      )}
    </div>
  )
}

export function RunResultsView({ runId }: RunResultsViewProps) {
  const { runSplit, setRunSplit } = useLayoutStore()
  const run = useRunStreamStore(s => s.runsById[runId])

  // v2 run detection: presence of populated phases map marks this as a v2 run
  const isV2Run = run != null && Object.keys(run.phases ?? {}).length > 0

  // Tactician filter propagated down to StreamingCardList
  const [tacticianFilter, setTacticianFilter] = useState<{ phaseId: string; slotIdx: number } | null>(null)
  const [shareOpen, setShareOpen] = useState(false)

  const handleLayout = useCallback(
    (sizes: number[]) => {
      if (sizes.length === 2) {
        setRunSplit({ top: sizes[0], bottom: sizes[1] })
      }
    },
    [setRunSplit],
  )

  // Simple mobile check — not reactive, just guards initial render
  const isMobile =
    typeof window !== 'undefined' && window.innerWidth <= 768

  if (isMobile) {
    return (
      <div className="flex flex-col h-full">
        <DebugBadge runId={runId} />
        {isV2Run && (
          <div className="border-b border-slate-800 flex-shrink-0">
            <PhaseDAGView runId={runId} onSelectTactician={setTacticianFilter} />
          </div>
        )}
        <div className="flex-1 overflow-hidden">
          <StreamingCardList runId={runId} filterByTactician={tacticianFilter ?? undefined} />
        </div>
        {!isV2Run && (
          <details className="border-t border-border">
            <summary className="px-4 py-2 text-xs text-muted-foreground cursor-pointer select-none">
              Flow Diagram ▸
            </summary>
            <div className="h-48">
              <FlowMiniPreview runId={runId} />
            </div>
          </details>
        )}
      </div>
    )
  }

  return (
    <PanelGroup
      direction="vertical"
      onLayout={handleLayout}
      className="h-full"
    >
      <Panel
        defaultSize={runSplit.top}
        minSize={30}
        className="overflow-hidden"
      >
        <div className="flex flex-col h-full">
          {/* Header row: DebugBadge + Share button */}
          <div className="relative flex-shrink-0">
            <DebugBadge runId={runId} />
            <button
              data-testid="share-run-button"
              onClick={() => setShareOpen(true)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm border border-border bg-card/60 hover:bg-card px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors"
              title="Share this run (read-only link)"
            >
              Share
            </button>
          </div>
          <ShareDialog runId={runId} open={shareOpen} onClose={() => setShareOpen(false)} />
          {/* v2 engine: show PhaseDAGView above the card list. Auto-height
              now that the swim lanes collapsed to a single subtitle row —
              the previous fixed 200px was leaving ~120px of dead space. */}
          {isV2Run && (
            <div className="border-b border-slate-800 flex-shrink-0">
              <PhaseDAGView runId={runId} onSelectTactician={setTacticianFilter} />
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <StreamingCardList runId={runId} filterByTactician={tacticianFilter ?? undefined} />
          </div>
          {/* Action row — Go Deeper / Analyze / Save as Pipeline. Visible
              once the run has streamed at least one terminal card so users
              know it's safe to follow up. ResultsPanel's identical row
              short-circuits behind RunResultsView for v2 runs, so we
              surface a parallel one here. */}
          <RunActionRow runId={runId} />
        </div>
      </Panel>

      <PanelResizeHandle className="h-1.5 bg-border hover:bg-violet-700/60 transition-colors cursor-row-resize relative group">
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 mx-auto w-8 h-0.5 rounded bg-border group-hover:bg-violet-500 transition-colors" />
      </PanelResizeHandle>

      <Panel
        defaultSize={runSplit.bottom}
        minSize={15}
        maxSize={60}
        className="overflow-hidden"
      >
        {/* Bottom panel: FlowMiniPreview — left-to-right flow graph of the
            run. (The investigation DAG view is available via the top panel's
            DAG toolbar button for users who want the full tree.) */}
        <FlowMiniPreview runId={runId} />
      </Panel>
    </PanelGroup>
  )
}

/** Inline action row for the v2 run view. Surfaces the post-run actions
 *  (Summary / Save as Pipeline / Download) without navigating to the legacy
 *  ResultsPanel. Reuses the same backend endpoints as ResultsPanel. */
function RunActionRow({ runId }: { runId: string }) {
  const run = useRunStreamStore((s) => s.runsById[runId])
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [savingPipeline, setSavingPipeline] = useState(false)

  // Run detail carries the research trail (findings / query / suggested_pipeline).
  const { data: detail } = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => getPipelineRun(runId),
  })
  const research = detail?.research ?? null

  // Only show once at least one card exists — gives users something to act on.
  const hasCards = run != null && run.cardOrder.length > 0
  if (!hasCards) return null

  async function handleSavePipeline() {
    if (!research) return
    setSavingPipeline(true)
    try {
      const sp = research.suggested_pipeline as any
      let pipelineData: { name: string; description: string; nodes: object[]; edges: object[] }
      if (sp && sp.nodes?.length > 0) {
        const nodeIds = sp.nodes.map(() => crypto.randomUUID())
        pipelineData = {
          name: sp.name,
          description: `Generated from IS research: "${research.query}"`,
          nodes: sp.nodes.map((n: any, i: number) => ({
            id: nodeIds[i], node_type: n.node_type, label: n.label,
            config: n.config ?? {}, position_y: i,
          })),
          edges: (sp.edges ?? []).map((e: any) => ({
            source_node_id: nodeIds[e.source_index],
            target_node_id: nodeIds[e.target_index],
          })),
        }
      } else {
        const nodeId = crypto.randomUUID()
        pipelineData = {
          name: `IS Research: ${research.query?.slice(0, 50) ?? 'Research'}`,
          description: `Saved from IS research run. Query: "${research.query}"`,
          nodes: [{
            id: nodeId, node_type: 'intelligent_search', label: 'Intelligent Search',
            config: { query: research.query ?? '' }, position_y: 0,
          }],
          edges: [],
        }
      }
      const result = await createPipeline(pipelineData as any)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      navigate(`/pipeline/${result.id}`)
    } catch (err) {
      console.error('Failed to save pipeline:', err)
    } finally {
      setSavingPipeline(false)
    }
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-t border-border/40 bg-card/30 flex-shrink-0">
      <button
        type="button"
        disabled
        className="text-[11px] font-semibold px-3 py-1.5 rounded border border-border/40 bg-card/30 text-muted-foreground/60 cursor-not-allowed"
        title="Go Deeper — coming soon"
      >
        ↳ Go Deeper
      </button>
      <button
        type="button"
        className="text-[11px] font-semibold px-3 py-1.5 rounded border border-sky-500/40 bg-sky-950/40 text-sky-200 hover:bg-sky-900/60 transition-colors"
        title="Summarise all findings into a narrative briefing"
        onClick={() => setSummaryOpen(true)}
      >
        ⌬ Summary
      </button>
      <button
        type="button"
        disabled={savingPipeline || !research}
        className="text-[11px] font-semibold px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-950/40 text-emerald-200 hover:bg-emerald-900/60 disabled:opacity-50 transition-colors"
        title="Template this run as a reusable pipeline"
        onClick={handleSavePipeline}
      >
        {savingPipeline ? '⎘ Saving…' : '⎘ Save as Pipeline'}
      </button>
      <div className="ml-auto flex items-center gap-2">
        <DownloadMenu runId={runId} />
      </div>
      <SummaryModal runId={runId} open={summaryOpen} onClose={() => setSummaryOpen(false)} />
    </div>
  )
}
