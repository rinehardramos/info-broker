import React from 'react'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { DagPreview } from '@/components/pipeline/DagPreview'
import { ResearchFlow } from '@/components/results/ResearchFlow'
import type { RunEdge } from '@/stores/runStreamStore'
import type { PipelineNodeOut, PipelineEdgeOut, PipelineStepRun } from '@/api/pipelines'

interface FlowFullscreenOverlayProps {
  open: boolean
  onClose: () => void
  runId: string
  kind: 'pipeline' | 'is'
  extraEdges: RunEdge[]
  // Pipeline-kind only — nodes/edges from the pipeline definition
  pipelineNodes?: PipelineNodeOut[]
  pipelineEdges?: PipelineEdgeOut[]
  stepRuns?: PipelineStepRun[]
}

export function FlowFullscreenOverlay({
  open,
  onClose,
  runId,
  kind,
  extraEdges,
  pipelineNodes = [],
  pipelineEdges = [],
  stepRuns = [],
}: FlowFullscreenOverlayProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="max-w-none w-screen h-screen rounded-none border-none p-0 bg-background cursor-zoom-out"
        onClick={onClose}
        title="Click to return to split view"
        aria-label="Flow diagram fullscreen — click to collapse"
      >
        <div
          className="absolute top-4 left-4 z-10 flex items-center gap-2"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded bg-muted border border-border text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
          >
            ⊡ Collapse
          </button>
          <span className="text-xs text-muted-foreground">or click diagram</span>
        </div>
        <div className="w-full h-full flex items-center justify-center p-8 pointer-events-none">
          {kind === 'is' ? (
            <ResearchFlow runId={runId} extraEdges={extraEdges} />
          ) : (
            <DagPreview
              nodes={pipelineNodes}
              edges={pipelineEdges}
              stepRuns={stepRuns}
              extraEdges={extraEdges}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
