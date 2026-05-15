import React from 'react'
import type { ACHMatrix as ACHMatrixType, ACHMark } from '@/types/research'

interface ACHMatrixProps {
  matrix: ACHMatrixType
}

const MARK_SYMBOL: Record<ACHMark, string> = {
  consistent: '✓',
  inconsistent: '✗',
  neutral: '–',
  unknown: '?',
}

const MARK_CLASSES: Record<ACHMark, string> = {
  consistent: 'text-green-600 dark:text-green-400 font-bold',
  inconsistent: 'text-red-500 dark:text-red-400 font-bold',
  neutral: 'text-muted-foreground',
  unknown: 'text-muted-foreground/50',
}

const MARK_TOOLTIP: Record<ACHMark, string> = {
  consistent: 'Consistent — finding supports this hypothesis on this signal',
  inconsistent: 'Inconsistent — disconfirm evidence contradicts this hypothesis',
  neutral: 'Neutral — finding mentions but does not confirm or disconfirm',
  unknown: 'Unknown — no relevant finding for this signal',
}

function scoreToColor(score: number): string {
  if (score >= 0.7) return 'text-green-600 dark:text-green-400 font-semibold'
  if (score >= 0.4) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-500 dark:text-red-400'
}

/**
 * ACHMatrix renders the full Heuer Analysis of Competing Hypotheses table.
 *
 * Rows: signals (with weight labels)
 * Columns: hypotheses (top-ranked first)
 * Cells: ✓/✗/–/? with hover tooltip showing the ACH mark meaning
 * Bottom row: final ACH scores per hypothesis
 */
export function ACHMatrix({ matrix }: ACHMatrixProps) {
  if (!matrix || matrix.hypotheses.length === 0) return null

  // Build lookup: (signal_id, hypothesis_name) → ACHCell
  const cellLookup = new Map<string, (typeof matrix.cells)[0]>()
  for (const cell of matrix.cells) {
    cellLookup.set(`${cell.signal_id}::${cell.hypothesis_name}`, cell)
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider min-w-[140px]">
              Signal
            </th>
            <th className="text-center px-2 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider w-14">
              Weight
            </th>
            {matrix.hypotheses.map((h) => (
              <th
                key={h}
                className="text-center px-2 py-2 text-[10px] font-semibold text-foreground/80 max-w-[90px] truncate"
                title={h}
              >
                {h.length > 14 ? h.slice(0, 12) + '…' : h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.signals.map((signal, rowIdx) => (
            <tr
              key={signal.id}
              className={rowIdx % 2 === 0 ? 'bg-transparent' : 'bg-muted/10'}
            >
              <td className="px-3 py-1.5 text-foreground/80 font-medium">
                {signal.label}
              </td>
              <td className="px-2 py-1.5 text-center text-muted-foreground">
                {(signal.weight * 100).toFixed(0)}%
              </td>
              {matrix.hypotheses.map((hypothesis) => {
                const cell = cellLookup.get(`${signal.id}::${hypothesis}`)
                const mark: ACHMark = cell?.mark ?? 'unknown'
                const tooltip = cell?.evidence_finding_id
                  ? `${MARK_TOOLTIP[mark]}\nEvidence: ${cell.evidence_finding_id}`
                  : MARK_TOOLTIP[mark]
                return (
                  <td
                    key={hypothesis}
                    className={`text-center px-2 py-1.5 cursor-default select-none ${MARK_CLASSES[mark]}`}
                    title={tooltip}
                  >
                    {MARK_SYMBOL[mark]}
                  </td>
                )
              })}
            </tr>
          ))}

          {/* Score row */}
          <tr className="border-t border-border bg-muted/20">
            <td className="px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider" colSpan={2}>
              ACH Score
            </td>
            {matrix.hypotheses.map((hypothesis) => {
              const score = matrix.scores[hypothesis] ?? 0
              return (
                <td
                  key={hypothesis}
                  className={`text-center px-2 py-2 text-xs ${scoreToColor(score)}`}
                  title={`ACH score for ${hypothesis}: ${(score * 100).toFixed(1)}%`}
                >
                  {(score * 100).toFixed(0)}%
                </td>
              )
            })}
          </tr>
        </tbody>
      </table>

      <p className="px-3 py-1.5 text-[9px] text-muted-foreground/60 italic border-t border-border">
        ✓ consistent · ✗ inconsistent · – neutral · ? unknown — per Heuer ACH methodology
      </p>
    </div>
  )
}
