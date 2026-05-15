/**
 * EstimateBreakdown — inline expandable that explains the RU number.
 *
 * Shows the collapsed summary ("~9 RU · ~4 min · ~12 tool calls") and,
 * when expanded, displays the formula factors so power users can see
 * exactly what each dial contributes.
 *
 * Example expanded: "9 RU = base 12 × speed×1.0 × cap×1.0 × res×1.0 × depth×1.0 × hyp×0.7"
 */
import { useState } from 'react'
import type { PreflightEstimate, PreflightEnvelope } from '../../hooks/usePreflight'

// Multiplier tables mirror app/pipeline/estimator.py exactly.
const SPEED_MULT: Record<string, number> = {
  slow: 0.9,
  normal: 1.0,
  fast: 1.15,
  very_fast: 1.4,
  extreme: 1.8,
}

const CAP_MULT: Record<string, number> = {
  light: 0.5,
  general: 1.0,
  high: 1.8,
}

const RESOURCE_MULT: Record<string, number> = {
  tiny: 0.5,
  light: 0.7,
  medium: 1.0,
  heavy: 1.4,
  unlimited: 2.0,
}

const DEPTH_MULT: Record<string, number> = {
  shallow: 0.7,
  search: 1.0,
  deep: 1.6,
  abyss: 2.5,
}

const HYP_MULT: Record<string, number> = {
  single: 1.0,
  paired: 1.5,
  competing: 2.2,
  adversarial: 3.5,
  swarm: 5.5,
}

// Base RU per strategy — must stay in sync with estimator.py
const BASE_RU: Record<string, number> = {
  media_identification: 12,
}

interface EstimateBreakdownProps {
  estimate: PreflightEstimate
  envelope: PreflightEnvelope
  strategy: string
}

export function EstimateBreakdown({ estimate, envelope, strategy }: EstimateBreakdownProps) {
  const [expanded, setExpanded] = useState(false)

  const base = BASE_RU[strategy] ?? 12
  const sm = SPEED_MULT[envelope.speed] ?? 1.0
  const cm = CAP_MULT[envelope.capability] ?? 1.0
  const rm = RESOURCE_MULT[envelope.resource] ?? 1.0
  const dm = DEPTH_MULT[envelope.depth] ?? 1.0
  const hm = HYP_MULT[envelope.hypothesis_count] ?? 2.2
  const usd = (estimate.estimated_ru * 0.1).toFixed(2)
  const mins = Math.round(estimate.est_wall_time_s / 60)

  return (
    <div style={{ marginBottom: 10, fontSize: 12, color: 'var(--muted)' }}>
      <span>
        Estimate: ~{estimate.estimated_ru} RU (${usd})
        {' · '}~{mins} min
        {' · '}~{estimate.est_tool_calls} tool calls
      </span>
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          marginLeft: 6,
          fontSize: 10,
          color: 'var(--muted)',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textDecoration: 'underline',
        }}
        aria-expanded={expanded}
      >
        {expanded ? 'hide' : 'why?'}
      </button>

      {expanded && (
        <div
          style={{
            marginTop: 6,
            padding: '6px 10px',
            borderLeft: '2px solid var(--border)',
            fontSize: 11,
            lineHeight: 1.6,
            color: 'var(--muted)',
          }}
        >
          <div style={{ fontFamily: 'monospace', marginBottom: 4 }}>
            {estimate.estimated_ru} RU = base {base}
            {' × '}speed×{sm}
            {' × '}cap×{cm}
            {' × '}res×{rm}
            {' × '}depth×{dm}
            {' × '}hyp×{hm}
          </div>
          <div>p90 (worst-realistic): {estimate.estimated_ru_p90} RU — this is the wallet hold amount</div>
          <div>Branches: {estimate.est_branches} parallel tacticians</div>
        </div>
      )}
    </div>
  )
}
