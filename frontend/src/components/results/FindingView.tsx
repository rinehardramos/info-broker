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

/** Single row — title, snippet prose, confidence bar, source link, date. */
function FindingRow({
  finding,
  compact = false,
  clickable = false,
}: {
  finding: NormalizedFinding
  compact?: boolean
  clickable?: boolean
}) {
  const confPct = finding.confidence != null ? Math.round(finding.confidence * 100) : null
  return (
    <div
      className={
        'rounded-md border border-border/60 bg-card/40 p-2.5 space-y-1.5 ' +
        (clickable
          ? 'cursor-pointer hover:bg-card/70 hover:border-violet-700/50 transition-colors'
          : '')
      }
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-foreground truncate">{finding.candidate}</div>
          {finding.title && finding.title !== finding.candidate && (
            <div className="text-[11px] text-muted-foreground truncate mt-0.5">{finding.title}</div>
          )}
        </div>
        {finding.source_class && (
          <SourceClassBadge sourceClass={finding.source_class as SourceClass} compact />
        )}
      </div>

      {finding.evidence_snippet && !compact && (
        <p className="text-xs text-foreground/80 leading-relaxed">{finding.evidence_snippet}</p>
      )}

      <div className="flex items-center gap-2 pt-0.5">
        {confPct != null && (
          <div className="flex items-center gap-1.5 flex-1 max-w-[140px]">
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
        {finding.date && (
          <span className="text-[10px] text-muted-foreground/70">{finding.date.slice(0, 10)}</span>
        )}
        {finding.source_url && (
          <a
            href={finding.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="ml-auto text-[10px] text-sky-400 hover:underline truncate max-w-[140px]"
          >
            source ↗
          </a>
        )}
      </div>
    </div>
  )
}

interface FindingViewProps {
  data: unknown
  limit?: number
  compact?: boolean
  clickable?: boolean
}

/**
 * Render structured findings. Returns null when input doesn't match a
 * known shape — callers fall back to plain text in that case.
 *
 * (This is a React component, not a util — Fast Refresh friendly.)
 */
export function FindingView({ data, limit, compact, clickable }: FindingViewProps) {
  const findings = parseAndNormalize(data)
  if (!findings || findings.length === 0) return null

  const cap = limit ?? findings.length
  const visible = findings.slice(0, cap)
  const hiddenCount = findings.length - visible.length

  return (
    <div className="space-y-1.5">
      {visible.map((f, i) => (
        <FindingRow key={i} finding={f} compact={compact} clickable={clickable} />
      ))}
      {hiddenCount > 0 && (
        <div className="text-[10px] text-muted-foreground italic text-center pt-1">
          + {hiddenCount} more finding{hiddenCount !== 1 ? 's' : ''} (click to expand)
        </div>
      )}
    </div>
  )
}
