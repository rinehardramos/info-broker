/**
 * Finding normalization — extract a structured finding (or list) from any
 * input shape the brain might emit: a single dict, a list, an MCP envelope
 * `{result: ...}`, or a wrapper with `items` / `results` / `findings`.
 *
 * Lives in a separate non-component file so Vite Fast Refresh stays happy
 * with FindingView.tsx (which exports only React components).
 */
import type { SourceClass } from '@/types/research'

export interface NormalizedFinding {
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
    (typeof o.text === 'string' && o.text) ||
    (typeof o.content === 'string' && o.content) ||
    ''
  if (!candidate && !snippet) return null
  return {
    candidate: candidate || (snippet.slice(0, 60) + (snippet.length > 60 ? '…' : '')),
    source_class: typeof o.source_class === 'string' ? (o.source_class as SourceClass) : undefined,
    source_url:
      (typeof o.source_url === 'string' && o.source_url) ||
      (typeof o.url === 'string' && o.url) ||
      (typeof o.link === 'string' && o.link) ||
      (typeof o.href === 'string' && o.href) ||
      undefined,
    evidence_snippet: snippet,
    confidence: typeof o.confidence === 'number' ? o.confidence : undefined,
    title: typeof o.title === 'string' ? o.title : undefined,
    date:
      typeof o.date === 'string'
        ? o.date
        : typeof o.published_at === 'string'
          ? o.published_at
          : undefined,
  }
}

export function normalizeFindings(obj: unknown): NormalizedFinding[] | null {
  if (!obj) return null
  const single = normalizeOne(obj)
  if (single) return [single]
  if (Array.isArray(obj)) {
    const list = obj.map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
    return list.length > 0 ? list : null
  }
  if (typeof obj === 'object') {
    const o = obj as Record<string, unknown>
    if (o.result) {
      const inner = normalizeFindings(o.result)
      if (inner) return inner
    }
    for (const key of ['items', 'results', 'findings']) {
      const arr = o[key]
      if (Array.isArray(arr)) {
        const list = arr.map(normalizeOne).filter((x): x is NormalizedFinding => x !== null)
        if (list.length > 0) return list
      }
    }
  }
  return null
}

/** Parse a JSON string if possible, then normalize. */
export function parseAndNormalize(data: unknown): NormalizedFinding[] | null {
  let parsed: unknown = data
  if (typeof data === 'string') {
    try {
      parsed = JSON.parse(data)
    } catch {
      return null
    }
  }
  return normalizeFindings(parsed)
}
