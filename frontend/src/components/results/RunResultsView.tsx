import React, { useCallback } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { StreamingCardList } from './StreamingCardList'
import { FlowMiniPreview } from './FlowMiniPreview'
import { useLayoutStore } from '@/stores/layoutStore'

interface RunResultsViewProps {
  runId: string
}

export function RunResultsView({ runId }: RunResultsViewProps) {
  const { runSplit, setRunSplit } = useLayoutStore()

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
        <div className="flex-1 overflow-hidden">
          <StreamingCardList runId={runId} />
        </div>
        <details className="border-t border-border">
          <summary className="px-4 py-2 text-xs text-muted-foreground cursor-pointer select-none">
            Flow Diagram ▸
          </summary>
          <div className="h-48">
            <FlowMiniPreview runId={runId} />
          </div>
        </details>
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
        <StreamingCardList runId={runId} />
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
        <FlowMiniPreview runId={runId} />
      </Panel>
    </PanelGroup>
  )
}
