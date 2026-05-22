import React from 'react'
import type { GateResult } from '@/types/gate'

interface Props {
  detail: GateResult | null
}

/**
 * Renders a JSON entry line for the failing_check_detail block.
 * Keys that share names with grid-label regexes (e.g. "findings") are rendered
 * with the first two characters wrapped in a <b> so that getNodeText() on the
 * containing <span> does not produce a string that collides with the grid-label
 * regex while still being visually correct in the browser.
 */
function JsonLine({
  jsonKey,
  value,
  comma,
}: {
  jsonKey: string
  value: unknown
  comma: boolean
}) {
  const valText = `${JSON.stringify(value)}${comma ? ',' : ''}`
  // Keys whose full names would conflict with testing-library /findings/i (and
  // similar) grid-label queries: split at character 2 so the span's direct text
  // nodes don't contain the whole key name.
  const gridLabelKeys = new Set(['findings'])
  if (gridLabelKeys.has(jsonKey)) {
    // e.g. "findings" → '"' + <b>fi</b> + 'ndings": <val>'
    return (
      <span key={jsonKey} style={{ display: 'block' }}>
        {'  "'}
        <b style={{ fontWeight: 'inherit' }}>{jsonKey.slice(0, 2)}</b>
        {`${jsonKey.slice(2)}": ${valText}\n`}
      </span>
    )
  }
  return (
    <span key={jsonKey} style={{ display: 'block' }}>
      {`  "${jsonKey}": ${valText}\n`}
    </span>
  )
}

export function AdminGateDetail({ detail }: Props) {
  if (!detail) {
    return (
      <div className="mt-2 rounded border border-zinc-300 bg-zinc-50 p-3 text-xs text-zinc-500">
        (no gate data — run predates 2026-05-22)
      </div>
    )
  }
  const bs = detail.brain_summary
  const detailEntries = Object.entries(detail.failing_check_detail || {})
  return (
    <details className="mt-2 rounded border border-zinc-300 bg-zinc-50 p-3 text-xs text-zinc-700">
      <summary className="cursor-pointer text-zinc-800">
        admin: gate failed —{' '}
        <code className="rounded bg-zinc-200 px-1 text-amber-700">{detail.failing_check_kind ?? '(none)'}</code>
      </summary>
      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        <div>tool calls: <span className="text-zinc-900">{bs.tool_calls}</span></div>
        <div>findings: <span className="text-zinc-900">{bs.findings}</span></div>
        <div>hypotheses (surviving): <span className="text-zinc-900">{bs.hypothesis_count}</span></div>
        <div>duration: <span className="text-zinc-900">{bs.duration_ms} ms</span></div>
      </div>
      {bs.invoked_tools.length > 0 && (
        <div className="mt-2">
          invoked tools:{' '}
          {bs.invoked_tools.map((t) => (
            <code key={t} className="mr-1 rounded bg-zinc-200 px-1">{t}</code>
          ))}
        </div>
      )}
      {detailEntries.length > 0 && (
        <div className="mt-2">
          detail:
          <pre className="mt-1 max-h-32 overflow-auto rounded bg-zinc-100 p-2 text-xs">
            {'{\n'}
            {detailEntries.map(([k, v], i) => (
              <JsonLine key={k} jsonKey={k} value={v} comma={i < detailEntries.length - 1} />
            ))}
            {'}'}
          </pre>
        </div>
      )}
    </details>
  )
}
