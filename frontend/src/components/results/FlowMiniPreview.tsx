import React, { useState } from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { ResearchFlow } from '@/components/results/ResearchFlow'
import { FlowFullscreenOverlay } from './FlowFullscreenOverlay'
import type { PipelineNodeOut, PipelineEdgeOut, PipelineStepRun } from '@/api/pipelines'

interface FlowMiniPreviewProps {
  runId: string
  // Pipeline-kind only — nodes/edges from the pipeline definition
  pipelineNodes?: PipelineNodeOut[]
  pipelineEdges?: PipelineEdgeOut[]
  stepRuns?: PipelineStepRun[]
}

export function FlowMiniPreview({
  runId,
  pipelineNodes = [],
  pipelineEdges = [],
  stepRuns = [],
}: FlowMiniPreviewProps) {
  const [fullscreen, setFullscreen] = useState(false)
  const run = useRunStreamStore((s) => s.runsById[runId])
  const extraEdges = run?.edges ?? []
  const kind = run?.kind ?? 'pipeline'
  const isRunning = run?.status === 'running'

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setFullscreen(true)}
        onKeyDown={(e) => e.key === 'Enter' && setFullscreen(true)}
        className="relative w-full h-full cursor-zoom-in bg-background/50 hover:bg-background/70 transition-colors overflow-hidden"
        title="Click to expand flow diagram"
      >
        {/* Placeholder/overlay only when there's no IS run to render — otherwise
            ResearchFlow shows its own header + progress bar. */}
        {kind !== 'is' && (
          <div className="absolute top-2 left-3 z-10 flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wide select-none">
            {isRunning && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            )}
            Flow Diagram {isRunning ? '(running)' : ''} · click to expand
          </div>
        )}
        <div className="w-full h-full pointer-events-none">
          {kind === 'is' ? (
            <ResearchFlow runId={runId} extraEdges={extraEdges} />
          ) : (
            <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
              Flow diagram available for IS runs
            </div>
          )}
        </div>
      </div>

      <FlowFullscreenOverlay
        open={fullscreen}
        onClose={() => setFullscreen(false)}
        runId={runId}
        kind={kind}
        extraEdges={extraEdges}
        pipelineNodes={pipelineNodes}
        pipelineEdges={pipelineEdges}
        stepRuns={stepRuns}
      />
    </>
  )
}
