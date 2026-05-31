import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getPipelineRun } from '../../api/pipelines'
import { runAnalyzer } from '../../api/v3'
import { AnalysisPanel } from './AnalysisPanel'

interface SummaryModalProps {
  runId: string
  open: boolean
  onClose: () => void
}

/** Cached, analyzer-backed summary of a run's findings.
 *
 * The analyzer endpoint (`/v3/research-trails/analyze`) runs in the background and
 * persists its result to `research_trails.analysis` — i.e. the cache. So:
 *  - if a saved analysis already exists, we show it instantly,
 *  - "Regenerate" re-runs the analyzer and we poll the run detail until the new
 *    analysis lands (the `_status` marker clears when real data is written).
 */
export function SummaryModal({ runId, open, onClose }: SummaryModalProps) {
  const qc = useQueryClient()
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: run } = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => getPipelineRun(runId),
    enabled: open,
    // While a generation is in flight, poll so the freshly-written analysis appears.
    refetchInterval: () => (generating ? 2500 : false),
  })

  const research = run?.research ?? null
  const findings = research?.findings ?? []
  const rawAnalysis = (research?.analysis ?? null) as any
  // A `_status` marker means "analyzing"/"failed" — not a real result.
  const analysis = rawAnalysis && !rawAnalysis._status ? rawAnalysis : null

  // Stop polling once the real analysis lands.
  if (generating && analysis) setGenerating(false)

  async function generate() {
    setError(null)
    setGenerating(true)
    try {
      await runAnalyzer(findings as object[], undefined, undefined, research?.query, runId)
      // The result is written asynchronously; the refetchInterval above picks it up.
      qc.invalidateQueries({ queryKey: ['pipeline-run', runId] })
    } catch (e) {
      setGenerating(false)
      setError(e instanceof Error ? e.message : 'Failed to generate summary')
    }
  }

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Run summary"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col p-6 shadow-2xl">
        <div className="flex items-center justify-between flex-shrink-0">
          <h2 className="text-sm font-semibold text-foreground">
            Summary
            {research?.query && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                "{research.query.slice(0, 60)}"
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {(analysis || findings.length > 0) && (
              <button
                type="button"
                onClick={generate}
                disabled={generating || findings.length === 0}
                className="text-[11px] font-semibold px-2.5 py-1 rounded border border-sky-500/40 bg-sky-950/40 text-sky-200 hover:bg-sky-900/60 disabled:opacity-50 transition-colors"
                title={findings.length === 0 ? 'No findings to summarize' : 'Re-run the analysis'}
              >
                {generating ? 'Generating…' : analysis ? 'Regenerate' : 'Generate'}
              </button>
            )}
            <button
              onClick={onClose}
              aria-label="Close"
              className="text-muted-foreground hover:text-foreground transition-colors text-lg leading-none"
            >
              ×
            </button>
          </div>
        </div>

        <div className="mt-4 overflow-y-auto flex-1 min-h-[120px]">
          {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
          {analysis ? (
            <AnalysisPanel analysis={analysis} />
          ) : generating ? (
            <p className="text-xs text-muted-foreground italic">
              Analyzing {findings.length} finding{findings.length === 1 ? '' : 's'}…
            </p>
          ) : findings.length === 0 ? (
            <p className="text-xs text-muted-foreground">No findings available to summarize yet.</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              No summary cached for this run. Click <span className="text-sky-300 font-medium">Generate</span> to
              analyze its {findings.length} finding{findings.length === 1 ? '' : 's'}.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
