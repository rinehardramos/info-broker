import { useState, useEffect, useCallback } from 'react'
import { usePreflight } from '../../hooks/usePreflight'
import type { DialsIn, ModeEntry } from '../../hooks/usePreflight'
import { ModePicker } from './ModePicker'
import { DialPicker } from './DialPicker'
import { EstimateBreakdown } from './EstimateBreakdown'
import { TemplateDropdown } from './TemplateDropdown'
import { SaveTemplateDialog } from './SaveTemplateDialog'
import { useTemplates } from '../../hooks/useTemplates'
import type { Template } from '../../hooks/useTemplates'

// ---------------------------------------------------------------------------
// Dial level constants — single source of truth for the UI
// ---------------------------------------------------------------------------

const SPEED_LEVELS = ['slow', 'normal', 'fast', 'very_fast', 'extreme'] as const
const CAPABILITY_LEVELS = ['light', 'general', 'high'] as const
const RESOURCE_LEVELS = ['tiny', 'light', 'medium', 'heavy', 'unlimited'] as const
const HYPOTHESIS_LEVELS = ['single', 'paired', 'competing', 'adversarial', 'swarm'] as const
const DEPTH_LEVELS = ['shallow', 'search', 'deep', 'abyss'] as const

// Strategy → hypothesis_count floor (mirrors backend _STRATEGY_HYPOTHESIS_FLOOR)
const STRATEGY_HYPOTHESIS_FLOOR: Record<string, string> = {
  media_identification: 'competing',
}

// ---------------------------------------------------------------------------
// Disabled-level computation for strategy budget minimums enforcement
// ---------------------------------------------------------------------------

function buildDisabledHypotheses(strategy: string): Set<string> {
  const floor = STRATEGY_HYPOTHESIS_FLOOR[strategy]
  if (!floor) return new Set()
  const floorIdx = HYPOTHESIS_LEVELS.indexOf(floor as typeof HYPOTHESIS_LEVELS[number])
  return new Set(HYPOTHESIS_LEVELS.filter((_, i) => i < floorIdx))
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
  const {
    preflight,
    preflightDebounced,
    confirm,
    estimate,
    isLoading,
    error,
    modes,
    userDefaults,
  } = usePreflight()

  // ---- dial state — seeded from per-user defaults when available ------------
  const [mode, setMode] = useState<string>('investigation')
  const [advanced, setAdvanced] = useState(false)
  const [speed, setSpeed] = useState<DialsIn['speed']>('normal')
  const [capability, setCapability] = useState<DialsIn['capability']>('general')
  const [resource, setResource] = useState<DialsIn['resource']>('medium')
  const [depth, setDepth] = useState<DialsIn['depth']>('search')
  const [hypothesisCount, setHypothesisCount] = useState<DialsIn['hypothesis_count']>('competing')
  const [showTopup, setShowTopup] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // Apply per-user defaults once they arrive (only if user hasn't touched dials yet)
  const defaultsApplied = useState(false)
  useEffect(() => {
    if (userDefaults && !defaultsApplied[0]) {
      defaultsApplied[1](true)
      if (userDefaults.speed) setSpeed(userDefaults.speed as DialsIn['speed'])
      if (userDefaults.capability) setCapability(userDefaults.capability as DialsIn['capability'])
      if (userDefaults.resource) setResource(userDefaults.resource as DialsIn['resource'])
      if (userDefaults.depth) setDepth(userDefaults.depth as DialsIn['depth'])
      if (userDefaults.hypothesis_count) setHypothesisCount(userDefaults.hypothesis_count as DialsIn['hypothesis_count'])
    }
  }, [userDefaults]) // eslint-disable-line react-hooks/exhaustive-deps
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [showSaveCta, setShowSaveCta] = useState(false)

  const { templates, isLoading: templatesLoading, createTemplate, useTemplate } = useTemplates()

  // ---- initial load ---------------------------------------------------------
  useEffect(() => {
    preflight({ query, mode, dials: { speed, capability, resource, hypothesis_count: hypothesisCount, depth } })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- dial-change debounced refresh ----------------------------------------
  const runPreflightDebounced = useCallback(() => {
    preflightDebounced({
      query,
      mode,
      dials: { speed, capability, resource, hypothesis_count: hypothesisCount, depth },
    })
  }, [query, mode, speed, capability, resource, hypothesisCount, depth, preflightDebounced])

  useEffect(() => {
    runPreflightDebounced()
  }, [speed, capability, resource, hypothesisCount, depth]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync hypothesis_count if backend upgraded it (strategy floor enforcement)
  useEffect(() => {
    if (estimate) {
      setMode(estimate.suggested_mode)
      if (estimate.envelope.hypothesis_count !== hypothesisCount) {
        setHypothesisCount(estimate.envelope.hypothesis_count as DialsIn['hypothesis_count'])
      }
    }
  }, [estimate]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- mode selection -------------------------------------------------------
  function handleModeSelect(modeEntry: ModeEntry) {
    const d = modeEntry.dial_defaults
    setMode(modeEntry.id)
    setSpeed(d.speed as DialsIn['speed'])
    setCapability(d.capability as DialsIn['capability'])
    setResource(d.resource as DialsIn['resource'])
    setDepth(d.depth as DialsIn['depth'])
    setHypothesisCount(d.hypothesis_count as DialsIn['hypothesis_count'])
    // Trigger fresh preflight with the new mode defaults immediately
    preflight({
      query,
      mode: modeEntry.id,
      dials: {
        speed: d.speed as DialsIn['speed'],
        capability: d.capability as DialsIn['capability'],
        resource: d.resource as DialsIn['resource'],
        depth: d.depth as DialsIn['depth'],
        hypothesis_count: d.hypothesis_count as DialsIn['hypothesis_count'],
      },
    })
  }

  // ---- template load --------------------------------------------------------
  function handleTemplateSelect(template: Template) {
    const env = template.envelope
    if (env.speed) setSpeed(env.speed as DialsIn['speed'])
    if (env.capability) setCapability(env.capability as DialsIn['capability'])
    if (env.resource) setResource(env.resource as DialsIn['resource'])
    if (env.depth) setDepth(env.depth as DialsIn['depth'])
    if (env.hypothesis_count) setHypothesisCount(env.hypothesis_count as DialsIn['hypothesis_count'])
    useTemplate(template.id)
    preflight({
      query,
      mode: env.mode ?? mode,
      dials: {
        speed: (env.speed as DialsIn['speed']) ?? speed,
        capability: (env.capability as DialsIn['capability']) ?? capability,
        resource: (env.resource as DialsIn['resource']) ?? resource,
        depth: (env.depth as DialsIn['depth']) ?? depth,
        hypothesis_count: (env.hypothesis_count as DialsIn['hypothesis_count']) ?? hypothesisCount,
      },
    })
  }

  async function handleSaveTemplate(name: string) {
    await createTemplate({
      name,
      query,
      envelope: { speed, capability, resource, depth, hypothesis_count: hypothesisCount, mode },
      strategy_id: strategy,
    })
  }

  // ---- derived values -------------------------------------------------------
  const insufficientRu = error === 'insufficient_ru' || error === 'below_floor'
  const strategy = estimate?.suggested_strategy ?? 'media_identification'
  const disabledHypotheses = buildDisabledHypotheses(strategy)
  const est = estimate?.estimate
  const wal = estimate?.wallet

  // ---- confirm + run --------------------------------------------------------
  async function handleRun() {
    if (!estimate) return
    setConfirming(true)
    setShowSaveCta(false)
    const result = await confirm({
      query,
      envelope: { speed, capability, resource, hypothesis_count: hypothesisCount, depth },
      strategy_id: strategy,
    })
    setConfirming(false)
    if (result) {
      setShowSaveCta(true)
      onConfirmed(result.run_id, result.hold_id)
    }
  }

  return (
    <>
      {showTopup && <TopupModal onClose={() => setShowTopup(false)} />}
      {showSaveDialog && (
        <SaveTemplateDialog
          existingNames={templates.map(t => t.name)}
          onSave={handleSaveTemplate}
          onClose={() => setShowSaveDialog(false)}
        />
      )}

      <div
        data-testid="preflight-panel"
        className="preflight-panel"
        style={{
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 16,
          maxWidth: 560,
          background: 'var(--background)',
          fontSize: 12,
        }}
      >
        {/* Template quick-pick */}
        <TemplateDropdown
          templates={templates}
          isLoading={templatesLoading}
          onSelect={handleTemplateSelect}
          onSaveRequest={() => setShowSaveDialog(true)}
        />

        {/* Mode picker — 6 modes in a pill row */}
        <ModePicker
          modes={modes}
          selectedMode={mode}
          onSelect={handleModeSelect}
        />

        {/* Strategy badge (read-only for MVP) */}
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

        {/* Advanced dials — 5 dials in a grid */}
        {advanced && (
          <div
            style={{
              marginBottom: 12,
              paddingLeft: 8,
              borderLeft: '2px solid var(--border)',
            }}
          >
            <DialPicker
              dial="speed"
              label="Speed"
              levels={SPEED_LEVELS}
              value={speed}
              onChange={v => setSpeed(v as DialsIn['speed'])}
            />
            <DialPicker
              dial="capability"
              label="Capability"
              levels={CAPABILITY_LEVELS}
              value={capability}
              onChange={v => setCapability(v as DialsIn['capability'])}
            />
            <DialPicker
              dial="resource"
              label="Resource"
              levels={RESOURCE_LEVELS}
              value={resource}
              onChange={v => setResource(v as DialsIn['resource'])}
            />
            <DialPicker
              dial="depth"
              label="Depth"
              levels={DEPTH_LEVELS}
              value={depth}
              onChange={v => setDepth(v as DialsIn['depth'])}
            />
            <DialPicker
              dial="hypothesis_count"
              label="Hypotheses"
              levels={HYPOTHESIS_LEVELS}
              value={hypothesisCount}
              onChange={v => setHypothesisCount(v as DialsIn['hypothesis_count'])}
              disabledLevels={disabledHypotheses}
              disabledTooltip={`This strategy requires ≥ ${STRATEGY_HYPOTHESIS_FLOOR[strategy] ?? 'competing'} for accurate results (per anti-tunneling rule)`}
            />
          </div>
        )}

        {/* Estimate breakdown */}
        {isLoading && (
          <div style={{ color: 'var(--muted)', marginBottom: 8 }}>Estimating...</div>
        )}

        {est && estimate && !isLoading && (
          <EstimateBreakdown
            estimate={est}
            envelope={estimate.envelope}
            strategy={strategy}
          />
        )}

        {/* Wallet balance + after-run projection */}
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

        {/* Strategy floor warnings from backend */}
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

        {/* Post-run: save as template CTA */}
        {showSaveCta && (
          <div
            style={{
              marginBottom: 8,
              padding: '6px 10px',
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: 'rgba(var(--accent-rgb, 99,102,241),0.06)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 11,
            }}
          >
            <span style={{ color: 'var(--muted)' }}>Save these settings as a template?</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => setShowSaveDialog(true)}
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 3,
                  border: 'none',
                  background: 'var(--accent)',
                  color: '#fff',
                  cursor: 'pointer',
                }}
              >
                Save
              </button>
              <button
                onClick={() => setShowSaveCta(false)}
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 3,
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  color: 'var(--muted)',
                  cursor: 'pointer',
                }}
              >
                Dismiss
              </button>
            </div>
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
            {confirming ? 'Holding RU...' : 'Run'}
          </button>
        </div>
      </div>
    </>
  )
}
