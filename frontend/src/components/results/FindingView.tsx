/**
 * FindingView — render a single finding (or list of findings) as a human-
 * readable card, NOT as JSON. Used inside NodeResultCard's body when the
 * card's output matches the finding shape, and inside the modal's
 * Formatted tab.
 *
 * Detected shapes:
 *   1. Single finding: { candidate, source_class, source_url, evidence_snippet, confidence }
 *   2. List of findings: array of the above OR { items: [...] }
 *   3. MCP wrapper: { result: {...} } where result is one of the above
 *
 * For anything that doesn't match, returns null so the caller can fall
 * back to plain text.
 */
import { SourceClassBadge } from './SourceClassBadge'
import type { SourceClass } from '@/types/research'

interface NormalizedFinding {
  candidate: string
  source_class?: SourceClass | string
  source_url?: string
  evidence_snippet: string
  confidence?: number
  title?: string
  date?: string
}

function normalizeOne(obj: unknown): NormalizedFinding | null {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null
  const o = obj as Record<string, unknown>
  const candidate =
    (typeof o.candidate === 'string' && o.candidate) ||
    (typeof o.candidate_name === 'string' && o.candidate_name) ||
    (typeof o.name === 'string' && o.name) ||
    (typeof o.title === 'string' && o.title) ||
    ''
  const snippet =
    (typeof o.evidence_snippet === 'string' && o.evidence_snippet) ||
    (typeof o.snippet === 'string' && o.snippet) ||
    (typeof o.summary === 'string' && o.summary) ||
    (typeof o.description === 'string' && o.description) ||
    ''
  // Need at least a candidate name or a substantive snippet to be a finding
  if (!candidate && !snippet) return null
  return {
    candidate: candidate || (snippet.slice(0, 60) + (snippet.length > 60 ? '…' : '')),
    source_class: typeof o.source_class === 'string' ? (o.source_class as SourceClass) : undefined,
    source_url:
      (typeof o.source_url === 'string' && o.source_url) ||
      (typeof o.url === 'string' && o.url) ||
      undefined,
    evidence_snippet: snippet,
    confidence: typeof o.confidence === 'number' ? o.confidence : undefined,
    title: typeof o.title === 'string' ? o.title : undefined,
    date: typeof o.date === 'string' ? o.date : (typeof o.published_at === 'string' ? o.published_at : undefined),
  }
}

function normalize(obj: unknown): NormalizedFinding[] | null {
  if (!obj) return null
  // Single finding
  const single = normalizeOne(obj)
  if (single) return [single]
  // Array of findings
  if (Array.isArray(obj)) {
    const list = obj.map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
    return list.length > 0 ? list : null
  }
  // MCP wrappers
  if (typeof obj === 'object') {
    const o = obj as Record<string, unknown>
    if (o.result) {
      const inner = normalize(o.result)
      if (inner) return inner
    }
    if (Array.isArray(o.items)) {
      const list = (o.items as unknown[]).map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
      return list.length > 0 ? list : null
    }
    if (Array.isArray(o.results)) {
      const list = (o.results as unknown[]).map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
      return list.length > 0 ? list : null
    }
    if (Array.isArray(o.findings)) {
      const list = (o.findings as unknown[]).map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
      return list.length > 0 ? list : null
    }
  }
  return null
}

/** Render a single finding as a structured card row. */
function FindingRow({ finding, compact = false }: { finding: NormalizedFinding; compact?: boolean }) {
  const confPct = finding.confidence != null ? Math.round(finding.confidence * 100) : null
  return (
    <div className="rounded-md border border-border/60 bg-card/40 p-2.5 space-y-1.5">
      {/* Title row */}
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

      {/* Evidence snippet — plain prose */}
      {finding.evidence_snippet && !compact && (
        <p className="text-xs text-foreground/80 leading-relaxed">
          {finding.evidence_snippet}
        </p>
      )}

      {/* Footer: confidence bar + date + link */}
      <div className="flex items-center gap-2 pt-0.5">
        {confPct != null && (
          <div className="flex items-center gap-1.5 flex-1 max-w-[140px]">
            <div className="flex-1 h-1 rounded bg-muted">
              <div
                className={
                  'h-1 rounded ' +
                  (confPct >= 70 ? 'bg-emerald-500' : confPct >= 40 ? 'bg-amber-500' : 'bg-rose-500')
                }
                style={{ width: `${confPct}%` }}
              />
            </div>
            <span className="text-[10px] font-mono tabular-nums text-muted-foreground">{confPct}%</span>
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
  /** Either a string (will JSON.parse) or a parsed object/array */
  data: unknown
  /** When true, only show the top N findings inline */
  limit?: number
  /** Tighter spacing when used inside a card body vs. modal */
  compact?: boolean
}

/** Returns null when data doesn't match a known finding shape. */
export function tryRenderFindings(data: unknown, options: { limit?: number; compact?: boolean } = {}) {
  let parsed: unknown = data
  if (typeof data === 'string') {
    try {
      parsed = JSON.parse(data)
    } catch {
      return null
    }
  }
  const findings = normalize(parsed)
  if (!findings || findings.length === 0) return null

  const limit = options.limit ?? findings.length
  const visible = findings.slice(0, limit)
  const hiddenCount = findings.length - visible.length

  return (
    <div className="space-y-1.5">
      {visible.map((f, i) => (
        <FindingRow key={i} finding={f} compact={options.compact} />
      ))}
      {hiddenCount > 0 && (
        <div className="text-[10px] text-muted-foreground italic text-center pt-1">
          + {hiddenCount} more finding{hiddenCount !== 1 ? 's' : ''} (click to expand)
        </div>
      )}
    </div>
  )
}

export function FindingView({ data, limit, compact }: FindingViewProps) {
  return tryRenderFindings(data, { limit, compact })
}
