import React, { useState } from 'react'
import { cn } from '@/lib/utils'
import type { RankedCandidate, SourceClass } from '@/types/research'
import { SourceClassBadge } from './SourceClassBadge'
import { EvidenceModal } from './EvidenceModal'

type SignalValue = 'match' | 'mismatch' | 'unknown' | undefined

function SignalCell({ value }: { value: SignalValue }) {
  if (value === 'match') {
    return <span className="text-emerald-400 text-sm font-semibold" title="Signal matched">✓</span>
  }
  if (value === 'mismatch') {
    return <span className="text-red-400 text-sm font-semibold" title="Signal did not match">✗</span>
  }
  // unknown or undefined — show neutral
  return <span className="text-muted-foreground text-sm" title="Signal unknown or untested">?</span>
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  return (
    <div className="flex items-center gap-1.5 min-w-[80px]">
      <div className="flex-1 h-1.5 rounded bg-muted/60">
        <div
          className="h-1.5 rounded bg-violet-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-violet-300 tabular-nums w-7 text-right">{pct}%</span>
    </div>
  )
}

function SourceBreakdownPills({ evidence }: { evidence: RankedCandidate['evidence'] }) {
  const counts: Partial<Record<SourceClass, number>> = {}
  for (const e of evidence) {
    counts[e.source_class] = (counts[e.source_class] ?? 0) + 1
  }

  const entries = Object.entries(counts) as [SourceClass, number][]
  if (entries.length === 0) {
    return <span className="text-muted-foreground text-[10px]">—</span>
  }

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {entries.map(([cls, count]) => (
        <span key={cls} className="inline-flex items-center gap-0.5">
          <SourceClassBadge sourceClass={cls} compact />
          <span className="text-[9px] text-muted-foreground tabular-nums">{count}</span>
        </span>
      ))}
    </div>
  )
}

interface CandidateRowProps {
  candidate: RankedCandidate
  isTop: boolean
  rank: number
  /** Run query — passed into EvidenceModal for entity profile enrichment. */
  context?: string
}

function uniqueDomainCount(evidence: RankedCandidate['evidence']): number {
  const hosts = new Set<string>()
  for (const e of evidence) {
    if (!e.source_url) continue
    try {
      const h = new URL(e.source_url).hostname.toLowerCase().replace(/^www\./, '')
      if (h) hosts.add(h)
    } catch { /* skip malformed URL */ }
  }
  return hosts.size
}

export function CandidateRow({ candidate, isTop, rank, context }: CandidateRowProps) {
  const [disconfirmOpen, setDisconfirmOpen] = useState(false)
  const [evidenceOpen,   setEvidenceOpen]   = useState(false)
  const disconfirmFindings = candidate.evidence.filter((e) => e.is_disconfirm)
  const evidenceCount = candidate.evidence.length
  const domainCount   = uniqueDomainCount(candidate.evidence)

  return (
    <div
      className={cn(
        'rounded-lg border transition-colors',
        isTop
          ? 'border-violet-700/60 bg-violet-950/20'
          : 'border-border bg-card/40',
      )}
    >
      {/* Main row — desktop-like 6-column layout via CSS grid */}
      <div className="grid grid-cols-[1fr_90px_32px_32px_32px_32px_80px] items-center gap-2 px-3 py-2.5 text-sm">
        {/* Candidate name + rank */}
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={cn(
              'text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0',
              isTop
                ? 'bg-violet-700 text-white'
                : 'bg-muted text-muted-foreground',
            )}
          >
            {rank}
          </span>
          <span
            className={cn(
              'font-medium truncate',
              isTop ? 'text-foreground' : 'text-foreground/80',
            )}
          >
            {candidate.name}
          </span>
          {isTop && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-violet-800/60 text-violet-300 font-semibold flex-shrink-0">
              top
            </span>
          )}
        </div>

        {/* Confidence bar */}
        <ConfidenceBar value={candidate.confidence} />

        {/* Signal columns */}
        <div className="flex justify-center"><SignalCell value={candidate.signal_scores?.primary} /></div>
        <div className="flex justify-center"><SignalCell value={candidate.signal_scores?.supporting} /></div>
        <div className="flex justify-center"><SignalCell value={candidate.signal_scores?.medium} /></div>
        <div className="flex justify-center"><SignalCell value={candidate.signal_scores?.recency} /></div>

        {/* Evidence count + source breakdown — click to open modal with full evidence list */}
        <button
          type="button"
          onClick={(ev) => { ev.stopPropagation(); setEvidenceOpen(true) }}
          disabled={evidenceCount === 0}
          className={cn(
            'flex flex-col gap-0.5 items-start text-left rounded px-1 -mx-1 transition-colors',
            evidenceCount > 0 ? 'cursor-pointer hover:bg-muted/40' : 'cursor-default opacity-60',
          )}
          title={evidenceCount > 0 ? 'View evidence' : 'No evidence'}
        >
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {evidenceCount} evidence
            {evidenceCount > 0 && (
              <span
                className={cn(
                  'ml-1',
                  domainCount >= 3 ? 'text-emerald-400'
                  : domainCount === 2 ? 'text-amber-400'
                  : 'text-muted-foreground/60',
                )}
                title={`${domainCount} unique source domain${domainCount === 1 ? '' : 's'}`}
              >
                · {domainCount} domain{domainCount === 1 ? '' : 's'}
              </span>
            )}
          </span>
          <SourceBreakdownPills evidence={candidate.evidence} />
        </button>
      </div>

      <EvidenceModal
        open={evidenceOpen}
        onClose={() => setEvidenceOpen(false)}
        candidate={candidate}
        context={context}
      />

      {/* "Why not X?" section — only shown for non-top candidates */}
      {!isTop && (
        <div className="border-t border-border/50 px-3 pb-2">
          <button
            type="button"
            onClick={() => setDisconfirmOpen((v) => !v)}
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors mt-1.5 flex items-center gap-1"
          >
            <span>{disconfirmOpen ? '▼' : '▶'}</span>
            <span>Why not {candidate.name}?</span>
            {disconfirmFindings.length > 0 && (
              <span className="ml-1 text-red-400">({disconfirmFindings.length} disconfirm)</span>
            )}
          </button>

          {disconfirmOpen && (
            <div className="mt-2 space-y-1.5">
              {disconfirmFindings.length === 0 ? (
                <p className="text-[10px] text-muted-foreground italic">
                  No disconfirm findings recorded for this candidate.
                </p>
              ) : (
                disconfirmFindings.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 bg-red-950/20 rounded px-2 py-1.5 border border-red-900/30">
                    <SourceClassBadge sourceClass={e.source_class} compact />
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] text-foreground/80 leading-relaxed line-clamp-3">
                        {e.snippet || 'No snippet available.'}
                      </p>
                      {e.source_url && (
                        <a
                          href={e.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[9px] text-sky-400 hover:underline truncate block mt-0.5"
                          onClick={(ev) => ev.stopPropagation()}
                        >
                          {e.source_url}
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
