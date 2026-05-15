import React, { useCallback, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { StreamingCardList } from './StreamingCardList'
import { FlowMiniPreview } from './FlowMiniPreview'
import { PhaseDAGView } from './PhaseDAGView'
import { InvestigationDAG } from './InvestigationDAG'
import { ShareDialog } from './ShareDialog'
import { useLayoutStore } from '@/stores/layoutStore'
import { useRunStreamStore } from '@/stores/runStreamStore'

interface RunResultsViewProps {
  runId: string
}

function DebugBadge({ runId }: { runId: string }) {
  const run = useRunStreamStore((s) => s.runsById[runId])
  const allIds = useRunStreamStore((s) => Object.keys(s.runsById))
  return (
    <div className="px-2 py-1 text-[9px] font-mono border-b border-border bg-amber-500/5 text-amber-500/80 flex items-center gap-2 select-text">
      <span title="Active runId from tab">run: <span className="text-amber-400">{runId.slice(0, 8)}</span></span>
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
          <div className="border-b border-slate-800 flex-shrink-0" style={{ height: 160 }}>
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
          {/* v2 engine: show PhaseDAGView above the card list */}
          {isV2Run && (
            <div className="border-b border-slate-800 flex-shrink-0" style={{ height: 200 }}>
              <PhaseDAGView runId={runId} onSelectTactician={setTacticianFilter} />
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <StreamingCardList runId={runId} filterByTactician={tacticianFilter ?? undefined} />
          </div>
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
        {/* v2 runs: show the InvestigationDAG (data is already in the
            runStreamStore: phases + tacticians + findings). Legacy runs:
            show the WebSocket-driven ResearchFlow as before. */}
        {isV2Run ? (
          <InvestigationDAG runId={runId} />
        ) : (
          <FlowMiniPreview runId={runId} />
        )}
      </Panel>
    </PanelGroup>
  )
}
