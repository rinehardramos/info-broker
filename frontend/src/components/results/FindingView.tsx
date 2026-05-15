/**
 * FindingView — render finding(s) as human-readable cards, NOT as JSON.
 *
 * Used inside NodeResultCard's body when the output matches the finding
 * shape, and inside the modal's Formatted tab. Normalization helpers live
 * in '@/lib/findings' so this file can export ONLY React components,
 * which keeps Vite Fast Refresh happy.
 */
import { SourceClassBadge } from './SourceClassBadge'
import type { SourceClass } from '@/types/research'
import { parseAndNormalize, type NormalizedFinding } from '@/lib/findings'

/** Extract a readable host from a URL string. */
function hostOf(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Strip a leading "N days ago - " / "N hours ago — " etc. from a snippet,
 *  since we already render the date as its own pill. Tools commonly prepend
 *  this, which reads as awkward concatenation in the UI. */
function cleanSnippet(snippet: string): string {
  return snippet
    .replace(/^\s*\d+\s*(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s+ago\s*[-–—:]?\s*/i, '')
    .replace(/^\s*&nbsp;\s*&nbsp;\s*/g, '')
    .replace(/&nbsp;/g, ' ')
    .trim()
}

/** Single row — proper search-result card with hierarchy:
 *   row 1: source host + date + (source_class badge)
 *   row 2: title (bold, the primary handle)
 *   row 3: snippet (prose, line-clamped)
 *   row 4: confidence bar + source-link footer */
function FindingRow({
  finding,
  compact = false,
  clickable = false,
  onSelect,
}: {
  finding: NormalizedFinding
  compact?: boolean
  clickable?: boolean
  onSelect?: () => void
}) {
  const confPct = finding.confidence != null ? Math.round(finding.confidence * 100) : null
  const host = finding.source_url ? hostOf(finding.source_url) : null
  const snippet = finding.evidence_snippet ? cleanSnippet(finding.evidence_snippet) : ''
  return (
    <div
      onClick={onSelect ? (e) => { e.stopPropagation(); onSelect() } : undefined}
      className={
        'rounded-lg border border-border/50 bg-card/50 p-3.5 space-y-2 ' +
        (clickable || onSelect
          ? 'cursor-pointer hover:bg-card/80 hover:border-violet-700/50 transition-colors'
          : '')
      }
    >
      {/* Metadata strip — host · date · source-class */}
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
        {host && (
          <span className="font-mono tracking-tight truncate max-w-[200px]" title={finding.source_url ?? ''}>
            {host}
          </span>
        )}
        {host && finding.date && <span className="opacity-40">·</span>}
        {finding.date && <span>{finding.date.slice(0, 10)}</span>}
        {finding.source_class && (
          <span className="ml-auto">
            <SourceClassBadge sourceClass={finding.source_class as SourceClass} compact />
          </span>
        )}
      </div>

      {/* Title — the primary candidate handle */}
      <div className="text-sm font-semibold text-foreground leading-snug">
        {finding.candidate}
      </div>
      {finding.title && finding.title !== finding.candidate && (
        <div className="text-[11px] text-muted-foreground/80 -mt-1">{finding.title}</div>
      )}

      {/* Snippet — readable prose */}
      {snippet && !compact && (
        <p className="text-[13px] text-foreground/80 leading-relaxed line-clamp-4">
          {snippet}
        </p>
      )}

      {/* Footer — confidence bar + source link */}
      {(confPct != null || finding.source_url) && (
        <div className="flex items-center gap-3 pt-1 border-t border-border/30">
          {confPct != null && (
            <div className="flex items-center gap-1.5 flex-1 max-w-[160px]">
              <div className="flex-1 h-1 rounded bg-muted">
                <div
                  className={
                    'h-1 rounded ' +
                    (confPct >= 70
                      ? 'bg-emerald-500'
                      : confPct >= 40
                        ? 'bg-amber-500'
                        : 'bg-rose-500')
                  }
                  style={{ width: `${confPct}%` }}
                />
              </div>
              <span className="text-[10px] font-mono tabular-nums text-muted-foreground">
                {confPct}%
              </span>
            </div>
          )}
          {finding.source_url && (
            <a
              href={finding.source_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="ml-auto text-[11px] text-sky-400 hover:underline inline-flex items-center gap-1"
            >
              Open source <span aria-hidden>↗</span>
            </a>
          )}
        </div>
      )}
    </div>
  )
}

interface FindingViewProps {
  data: unknown
  limit?: number
  compact?: boolean
  clickable?: boolean
  /** Optional — fires when a row is clicked. Takes precedence over relying
   *  on click bubbling to a parent onClick. */
  onSelect?: () => void
}

/**
 * Render structured findings. Returns null when input doesn't match a
 * known shape — callers fall back to plain text in that case.
 *
 * (This is a React component, not a util — Fast Refresh friendly.)
 */
export function FindingView({ data, limit, compact, clickable, onSelect }: FindingViewProps) {
  const findings = parseAndNormalize(data)
  if (!findings || findings.length === 0) return null

  const cap = limit ?? findings.length
  const visible = findings.slice(0, cap)
  const hiddenCount = findings.length - visible.length

  return (
    <div className="space-y-2.5">
      {/* Summary strip */}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground pb-1 border-b border-border/30">
        <span>
          <span className="font-semibold text-foreground/90">{findings.length}</span> result{findings.length !== 1 ? 's' : ''}
        </span>
        {hiddenCount > 0 && (
          <span className="italic">showing {visible.length} of {findings.length}</span>
        )}
      </div>
      {visible.map((f, i) => (
        <FindingRow key={i} finding={f} compact={compact} clickable={clickable} onSelect={onSelect} />
      ))}
    </div>
  )
}
