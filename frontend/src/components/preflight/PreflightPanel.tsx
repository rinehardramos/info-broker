import { useState, useEffect, useCallback } from 'react'
import { usePreflight } from '../../hooks/usePreflight'
import type { DialsIn, PreflightResult } from '../../hooks/usePreflight'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CAPABILITY_LEVELS = ['light', 'general', 'high'] as const
const HYPOTHESIS_LEVELS = ['single', 'paired', 'competing', 'adversarial', 'swarm'] as const
const DEPTH_LEVELS = ['shallow', 'search', 'deep', 'abyss'] as const

// Strategies that enforce a hypothesis_count floor
const STRATEGY_HYPOTHESIS_FLOOR: Record<string, string> = {
  media_identification: 'competing',
}

function isHypothesisDisabled(strategy: string, level: string): boolean {
  const floor = STRATEGY_HYPOTHESIS_FLOOR[strategy]
  if (!floor) return false
  const floorIdx = HYPOTHESIS_LEVELS.indexOf(floor as typeof HYPOTHESIS_LEVELS[number])
  const levelIdx = HYPOTHESIS_LEVELS.indexOf(level as typeof HYPOTHESIS_LEVELS[number])
  return levelIdx < floorIdx
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabledOptions,
  disabledTooltip,
}: {
  options: readonly T[]
  value: T
  onChange: (v: T) => void
  disabledOptions?: Set<T>
  disabledTooltip?: string
}) {
  return (
    <div style={{ display: 'flex', gap: 2 }}>
      {options.map(opt => {
        const disabled = disabledOptions?.has(opt) ?? false
        return (
          <button
            key={opt}
            disabled={disabled}
            title={disabled ? disabledTooltip : undefined}
            onClick={() => !disabled && onChange(opt)}
            style={{
              padding: '2px 8px',
              fontSize: 11,
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: value === opt ? 'var(--accent)' : 'transparent',
              color: disabled ? 'var(--muted)' : value === opt ? '#fff' : 'var(--foreground)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.45 : 1,
            }}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top-up placeholder modal
// TODO (post-MVP): replace with real Stripe top-up flow in v1.1
// ---------------------------------------------------------------------------

function TopupModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="topup-title"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--background)', border: '1px solid var(--border)',
          borderRadius: 8, padding: 24, maxWidth: 360, textAlign: 'center',
        }}
        onClick={e => e.stopPropagation()}
      >
        <h3 id="topup-title" style={{ marginBottom: 8, fontSize: 14 }}>Top-up coming in v1.1</h3>
        <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
          Automated top-up is not yet available. Please contact your administrator to add Research Units to your wallet.
        </p>
        <button
          onClick={onClose}
          style={{
            padding: '4px 16px', borderRadius: 4, fontSize: 12,
            border: '1px solid var(--border)', cursor: 'pointer',
            background: 'transparent', color: 'var(--foreground)',
          }}
        >
          Close
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface PreflightPanelProps {
  query: string
  onCancel: () => void
  /** Called with run_id + hold_id after a successful /preflight/confirm */
  onConfirmed: (runId: string, holdId: string) => void
}

export function PreflightPanel({ query, onCancel, onConfirmed }: PreflightPanelProps) {
  const { preflight, confirm, estimate, isLoading, error } = usePreflight()

  const [mode, setMode] = useState<'quick_lookup' | 'investigation'>('investigation')
  const [advanced, setAdvanced] = useState(false)
  const [capability, setCapability] = useState<DialsIn['capability']>('general')
  const [hypothesisCount, setHypothesisCount] = useState<DialsIn['hypothesis_count']>('competing')
  const [depth, setDepth] = useState<DialsIn['depth']>('search')
  const [showTopup, setShowTopup] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // Run preflight on mount and whenever dials change
  const runPreflight = useCallback(async () => {
    const result: PreflightResult | null = await preflight({
      query,
      mode,
      dials: { capability, hypothesis_count: hypothesisCount, depth },
    })
    if (result) {
      // Sync mode from backend suggestion on first load (before user changes it)
      setMode(result.suggested_mode as 'quick_lookup' | 'investigation')
      // Sync hypothesis_count if backend upgraded it
      if (result.envelope.hypothesis_count !== hypothesisCount) {
        setHypothesisCount(result.envelope.hypothesis_count as DialsIn['hypothesis_count'])
      }
    }
  }, [query, mode, capability, hypothesisCount, depth]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    runPreflight()
  }, [capability, hypothesisCount, depth]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initial load
  useEffect(() => {
    preflight({ query, mode, dials: { capability, hypothesis_count: hypothesisCount, depth } })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const insufficientRu = error === 'insufficient_ru' || error === 'below_floor'
  const strategy = estimate?.suggested_strategy ?? 'media_identification'

  const disabledHypotheses = new Set(
    HYPOTHESIS_LEVELS.filter(h => isHypothesisDisabled(strategy, h))
  )

  async function handleRun() {
    if (!estimate) return
    setConfirming(true)
    const result = await confirm({
      query,
      envelope: { capability, hypothesis_count: hypothesisCount, depth },
      strategy_id: strategy,
    })
    setConfirming(false)
    if (result) {
      onConfirmed(result.run_id, result.hold_id)
    }
  }

  const est = estimate?.estimate
  const wal = estimate?.wallet

  return (
    <>
      {showTopup && <TopupModal onClose={() => setShowTopup(false)} />}

      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 16,
          maxWidth: 520,
          background: 'var(--background)',
          fontSize: 12,
        }}
      >
        {/* Mode picker */}
        <div style={{ marginBottom: 12 }}>
          <span style={{ fontWeight: 600, marginRight: 8 }}>Mode</span>
          {(['quick_lookup', 'investigation'] as const).map(m => (
            <label key={m} style={{ marginRight: 10, cursor: 'pointer' }}>
              <input
                type="radio"
                name="preflight-mode"
                value={m}
                checked={mode === m}
                onChange={() => setMode(m)}
                style={{ marginRight: 4 }}
              />
              {m}
            </label>
          ))}
        </div>

        {/* Strategy badge */}
        <div style={{ marginBottom: 12 }}>
          <span style={{ fontWeight: 600, marginRight: 8 }}>Strategy</span>
          <span
            style={{
              background: 'var(--accent)', color: '#fff',
              borderRadius: 4, padding: '1px 8px', fontSize: 11,
            }}
          >
            {strategy}
          </span>
          <button
            onClick={() => setAdvanced(v => !v)}
            style={{
              marginLeft: 8, fontSize: 10, color: 'var(--muted)',
              background: 'transparent', border: 'none', cursor: 'pointer',
            }}
          >
            Advanced {advanced ? '▴' : '▾'}
          </button>
        </div>

        {/* Advanced dials */}
        {advanced && (
          <div style={{ marginBottom: 12, paddingLeft: 8, borderLeft: '2px solid var(--border)' }}>
            <div style={{ marginBottom: 6 }}>
              <span style={{ marginRight: 8 }}>Capability</span>
              <SegmentedControl
                options={CAPABILITY_LEVELS}
                value={capability}
                onChange={setCapability}
              />
            </div>
            <div>
              <span style={{ marginRight: 8 }}>Hypotheses</span>
              <SegmentedControl
                options={HYPOTHESIS_LEVELS}
                value={hypothesisCount}
                onChange={setHypothesisCount}
                disabledOptions={disabledHypotheses}
                disabledTooltip={`Strategy '${strategy}' requires at least 'competing' hypotheses for accuracy`}
              />
            </div>
          </div>
        )}

        {/* Estimate display */}
        {isLoading && <div style={{ color: 'var(--muted)', marginBottom: 8 }}>Estimating…</div>}

        {est && !isLoading && (
          <div style={{ marginBottom: 8, color: 'var(--muted)' }}>
            Estimate: ~{est.estimated_ru} RU (${(est.estimated_ru * 0.1).toFixed(2)})
            {' · '}~{Math.round(est.est_wall_time_s / 60)} min
            {' · '}~{est.est_tool_calls} tool calls
          </div>
        )}

        {wal && !isLoading && (
          <div style={{ marginBottom: 12, color: 'var(--muted)' }}>
            Wallet: {wal.available_ru} RU available
            {' → '}{wal.after_run_projection} RU after run
            {wal.after_run_projection < 0 && (
              <button
                onClick={() => setShowTopup(true)}
                style={{
                  marginLeft: 8, fontSize: 11, color: 'var(--accent)',
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Top up
              </button>
            )}
          </div>
        )}

        {/* Warnings */}
        {estimate?.warnings?.map((w, i) => (
          <div
            key={i}
            style={{
              marginBottom: 8, padding: '4px 8px', borderRadius: 4,
              background: 'rgba(255,200,0,0.1)', color: '#c07000', fontSize: 11,
            }}
          >
            {w}
          </div>
        ))}

        {/* Insufficient RU error */}
        {insufficientRu && (
          <div style={{ marginBottom: 8, color: '#c00', fontSize: 11 }}>
            Insufficient RU to run this configuration.{' '}
            <button
              onClick={() => setShowTopup(true)}
              style={{
                color: 'var(--accent)', background: 'transparent',
                border: 'none', cursor: 'pointer', textDecoration: 'underline',
              }}
            >
              Top up
            </button>
          </div>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onCancel}
            style={{
              padding: '4px 14px', borderRadius: 4, fontSize: 12,
              border: '1px solid var(--border)', background: 'transparent',
              color: 'var(--foreground)', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleRun}
            disabled={isLoading || confirming || !estimate}
            style={{
              padding: '4px 14px', borderRadius: 4, fontSize: 12,
              border: 'none', background: 'var(--accent)', color: '#fff',
              cursor: isLoading || confirming || !estimate ? 'not-allowed' : 'pointer',
              opacity: isLoading || confirming || !estimate ? 0.6 : 1,
            }}
          >
            {confirming ? 'Holding RU…' : 'Run'}
          </button>
        </div>
      </div>
    </>
  )
}
