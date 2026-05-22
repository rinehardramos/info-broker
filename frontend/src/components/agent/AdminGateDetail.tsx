import React from 'react'
import type { GateResult } from '@/types/gate'

interface Props {
  detail: GateResult | null
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
            {JSON.stringify(detail.failing_check_detail, null, 2)}
          </pre>
        </div>
      )}
    </details>
  )
}
