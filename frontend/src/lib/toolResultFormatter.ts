/**
 * Format raw tool-result text (often nested/double-encoded JSON from MCP) into
 * human-readable form and derive a result count from common shapes.
 *
 * MCP tools typically return text content like:
 *   {"result":"{\"status\":\"success\",\"items\":[{...}]}"}
 *
 * That's a JSON object whose 'result' value is *itself* a JSON-stringified
 * payload. The streaming preview shows the outer string verbatim — ugly.
 */

export interface FormattedToolResult {
  /** Pretty-printed text suitable for display. */
  pretty: string
  /** Result count extracted from shape (items.length, results.length, etc.) */
  count: number | null
  /** Whether parsing yielded a structured value (vs. plain text). */
  isStructured: boolean
}

/** Recursively unwrap any string that contains a JSON object/array. */
function unwrapNestedJson(value: unknown, depth = 0): unknown {
  if (depth > 4) return value
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    ) {
      try {
        return unwrapNestedJson(JSON.parse(trimmed), depth + 1)
      } catch {
        return value
      }
    }
    return value
  }
  if (Array.isArray(value)) {
    return value.map((v) => unwrapNestedJson(v, depth + 1))
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = unwrapNestedJson(v, depth + 1)
    }
    return out
  }
  return value
}

/** Pull a count from common 'list of things' shapes. */
function extractCount(parsed: unknown): number | null {
  if (Array.isArray(parsed)) return parsed.length
  if (parsed && typeof parsed === 'object') {
    const o = parsed as Record<string, unknown>
    // Common envelopes: {result: {...}}, {data: {...}}
    if ('result' in o) {
      const inner = extractCount(o.result)
      if (inner !== null) return inner
    }
    if ('data' in o) {
      const inner = extractCount(o.data)
      if (inner !== null) return inner
    }
    // Direct array fields
    for (const key of ['items', 'results', 'documents', 'entries', 'matches', 'hits', 'findings']) {
      if (Array.isArray(o[key])) return (o[key] as unknown[]).length
    }
  }
  return null
}

/** Try to parse `raw` as NDJSON (newline-delimited JSON). Returns the array
 * of parsed values, or null when at least one line isn't valid JSON. */
function tryParseNdjson(raw: string): unknown[] | null {
  const lines = raw.split(/\n+/).map((l) => l.trim()).filter(Boolean)
  if (lines.length < 2) return null
  const parsed: unknown[] = []
  for (const line of lines) {
    if (!(line.startsWith('{') || line.startsWith('['))) return null
    try {
      parsed.push(JSON.parse(line))
    } catch {
      return null
    }
  }
  return parsed
}

/** Detect arrays of {type: "tool_reference", tool_name: "..."} which are
 * planning signals from the brain (tools it's considering), not findings.
 * These should render as a compact summary, not a JSON dump. */
function summarizeToolReferences(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0) return null
  const items = value as Array<Record<string, unknown>>
  if (!items.every((i) => i && typeof i === 'object' && i.type === 'tool_reference' && typeof i.tool_name === 'string')) {
    return null
  }
  const names = items.map((i) => {
    const t = i.tool_name as string
    // Strip MCP prefix (mcp__server__tool → tool)
    const stripped = t.replace(/^mcp__[^_]+(?:-[^_]+)*__/, '')
    return stripped.replace(/^run_/, '')
  })
  return `Considered ${names.length} tool${names.length === 1 ? '' : 's'}: ${names.join(', ')}`
}

export function formatToolResult(raw: string | null | undefined): FormattedToolResult {
  const text = (raw ?? '').toString()
  if (!text.trim()) {
    return { pretty: '', count: null, isStructured: false }
  }

  // First: NDJSON (multiple JSON values per line — common from MCP tools that
  // emit one text block per item).
  const ndjson = tryParseNdjson(text)
  if (ndjson) {
    const unwrapped = ndjson.map((v) => unwrapNestedJson(v))
    const toolRefSummary = summarizeToolReferences(unwrapped)
    if (toolRefSummary !== null) {
      return { pretty: toolRefSummary, count: unwrapped.length, isStructured: false }
    }
    return {
      pretty: unwrapped.map((v) => JSON.stringify(v, null, 2)).join('\n'),
      count: unwrapped.length,
      isStructured: true,
    }
  }

  // Then: single JSON value (possibly nested-encoded).
  const parsed = unwrapNestedJson(text)
  if (typeof parsed === 'string') {
    // Couldn't parse — return as-is
    return { pretty: text, count: null, isStructured: false }
  }

  // Special-case tool_reference arrays (planning signals, not findings)
  const toolRefSummary = summarizeToolReferences(parsed)
  if (toolRefSummary !== null) {
    return { pretty: toolRefSummary, count: Array.isArray(parsed) ? parsed.length : null, isStructured: false }
  }

  let pretty: string
  try {
    pretty = JSON.stringify(parsed, null, 2)
  } catch {
    pretty = text
  }

  return {
    pretty,
    count: extractCount(parsed),
    isStructured: true,
  }
}
