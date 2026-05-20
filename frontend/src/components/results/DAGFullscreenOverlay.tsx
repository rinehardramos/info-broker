import { Dialog, DialogContent } from '@/components/ui/dialog'
import { InvestigationDAG } from '@/components/results/InvestigationDAG'

interface Props {
  open: boolean
  onClose: () => void
  runId: string
  onSelectTactician?: (filter: { phaseId: string; slotIdx: number } | null) => void
}

export function DAGFullscreenOverlay({ open, onClose, runId, onSelectTactician }: Props) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="max-w-none w-screen h-screen rounded-none border-none p-0 bg-background cursor-zoom-out"
        onClick={onClose}
        title="Click to collapse"
        aria-label="DAG diagram fullscreen — click to collapse"
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
        {/* InvestigationDAG manages its own pan/zoom; stretch it to fill the
            dialog so the graph uses the whole viewport. pointer-events-none
            preserves click-anywhere-to-collapse on the empty canvas. */}
        <div className="w-full h-full pt-16 px-6 pb-6">
          <div className="w-full h-full pointer-events-auto" onClick={(e) => e.stopPropagation()}>
            <InvestigationDAG runId={runId} onSelectTactician={onSelectTactician} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
