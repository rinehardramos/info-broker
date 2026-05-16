import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchSharedRun, SharedRun } from '@/hooks/useShare'
import { CandidateComparison } from '@/components/results/CandidateComparison'
import { SourceClassBadge } from '@/components/results/SourceClassBadge'
import type { RankedCandidate, SourceClass } from '@/types/research'

function Spinner() {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground text-sm py-20">
      Loading shared run…
    </div>
  )
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-20 gap-3">
      <p className="text-muted-foreground text-sm">This share link is invalid, expired, or has been revoked.</p>
      <a
        href="/"
        className="text-xs text-violet-400 hover:text-violet-300 underline transition-colors"
      >
        Sign up to run your own research
      </a>
    </div>
  )
}

/** Adapt the public SharedRun candidates into the RankedCandidate type expected by CandidateComparison. */
function adaptCandidates(shared: SharedRun): RankedCandidate[] {
  return shared.ranked_candidates.map((c) => ({
    name: c.name,
    confidence: c.confidence,
    signal_scores: c.signal_scores as RankedCandidate['signal_scores'],
    evidence: c.evidence.map((e) => ({
      source_class: e.source_class as SourceClass,
      source_url: e.source_url,
      snippet: e.snippet,
      is_disconfirm: e.is_disconfirm,
    })),
    slot_idx: c.slot_idx,
  }))
}

export default function SharedRunPage() {
  const { token } = useParams<{ token: string }>()
  const [run, setRun] = useState<SharedRun | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setNotFound(true)
      setLoading(false)
      return
    }
    fetchSharedRun(token)
      .then(setRun)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) return <div className="min-h-screen bg-background"><Spinner /></div>
  if (notFound || !run) return <div className="min-h-screen bg-background"><NotFound /></div>

  const candidates = adaptCandidates(run)
  const expiresDate = new Date(run.expires_at).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Minimal header — no nav */}
      <header className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">Shared run — read-only</span>
          <span className="text-sm font-medium text-foreground/90 truncate max-w-[60vw]">
            {run.query}
          </span>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] text-muted-foreground">
            {candidates.length} candidate{candidates.length !== 1 ? 's' : ''}
          </span>
          <span className="text-[10px] text-muted-foreground">
            Expires {expiresDate}
          </span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Candidate comparison (2+ candidates) or single-candidate view */}
        {candidates.length >= 2 ? (
          <CandidateComparison candidates={candidates} />
        ) : candidates.length === 1 ? (
          <SingleCandidateView candidate={candidates[0]} />
        ) : (
          <p className="text-sm text-muted-foreground text-center py-10">
            No candidate results available for this run.
          </p>
        )}

        {/* Phase findings (read-only source class badges) */}
        {run.phases.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-foreground/80 uppercase tracking-wider">
              Research findings by phase
            </h2>
            {run.phases.map((phase) => (
              <div key={phase.phase_id} className="rounded-lg border border-border bg-card/50 p-4 space-y-2">
                <p className="text-xs font-medium text-muted-foreground">{phase.phase_id}</p>
                <div className="space-y-1.5">
                  {phase.aggregated_findings.map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <SourceClassBadge sourceClass={f.source_class as SourceClass} compact />
                      <span className="text-foreground/80 flex-1">{f.evidence_summary || f.candidate_name}</span>
                      {f.confidence > 0 && (
                        <span className="text-muted-foreground shrink-0">{Math.round(f.confidence * 100)}%</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        )}
      </main>

      {/* Corner CTA — non-intrusive */}
      <div className="fixed bottom-4 right-4">
        <a
          href="/"
          className="block rounded-lg bg-violet-700/90 hover:bg-violet-700 px-4 py-2 text-xs font-medium text-white shadow-lg transition-colors"
        >
          Run your own research
        </a>
      </div>
    </div>
  )
}

function SingleCandidateView({ candidate }: { candidate: RankedCandidate }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{candidate.name}</span>
        <span className="text-xs text-muted-foreground">
          {Math.round(candidate.confidence * 100)}% confidence
        </span>
      </div>
      <div className="space-y-1.5">
        {candidate.evidence.map((ev, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <SourceClassBadge sourceClass={ev.source_class} compact />
            <span className={`flex-1 ${ev.is_disconfirm ? 'text-orange-400/80' : 'text-foreground/80'}`}>
              {ev.snippet}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
