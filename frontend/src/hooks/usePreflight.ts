import { useState, useCallback, useEffect, useRef } from 'react'
import { api } from '../api/client'

// ---------------------------------------------------------------------------
// Per-user default envelope (loaded on mount, used as initial dial state)
// ---------------------------------------------------------------------------

export interface UserDefaultEnvelope {
  speed?: string
  capability?: string
  resource?: string
  depth?: string
  hypothesis_count?: string
  mode?: string | null
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DialsIn {
  capability: 'light' | 'general' | 'high'
  hypothesis_count: 'single' | 'paired' | 'competing' | 'adversarial' | 'swarm'
  depth: 'shallow' | 'search' | 'deep' | 'abyss'
  speed: 'slow' | 'normal' | 'fast' | 'very_fast' | 'extreme'
  resource: 'tiny' | 'light' | 'medium' | 'heavy' | 'unlimited'
}

export interface PreflightIn {
  query: string
  mode?: string
  dials?: Partial<DialsIn>
  strategy?: string
  /** User-supplied override for auto-detected intent. */
  intent_override?: string
}

export interface IntentEntry {
  id: string
  label: string
}

export interface PreflightEstimate {
  estimated_ru: number
  estimated_ru_p90: number
  est_wall_time_s: number
  est_branches: number
  est_tool_calls: number
}

export interface PreflightEnvelope {
  capability: string
  hypothesis_count: string
  depth: string
  speed: string
  resource: string
  mode: string | null
}

export interface PreflightWallet {
  balance_ru: number
  held_ru: number
  available_ru: number
  after_run_projection: number
}

export interface PreflightResult {
  classifier_output: string
  suggested_strategy: string
  suggested_mode: string
  envelope: PreflightEnvelope
  estimate: PreflightEstimate
  wallet: PreflightWallet
  warnings: string[]
}

export interface PreflightConfirmIn {
  run_id?: string
  query: string
  envelope: Partial<DialsIn>
  strategy_id: string
  /** When true, backend launches engine_v2 in the background after the wallet hold. */
  start_run?: boolean
  /** Phase 2 (#75): skip the pre-run missing-key gate and launch anyway. */
  bypass_missing_keys?: boolean
}

export interface PreflightConfirmResult {
  run_id: string
  hold_id: string
  held_ru: number
}

/** Phase 2 (#75): one missing-key tool descriptor (NEVER carries a key value). */
export interface MissingKeyTool {
  technique_id: string
  key_name: string
  display_name: string
  setup_url: string
  setup_instructions: string
}

/** Returned by /preflight/confirm instead of starting the run when the chosen
 * strategy needs API keys that aren't configured. */
export interface PreflightGateResult {
  status: 'missing_keys_gate'
  run_id: string
  missing_tools: MissingKeyTool[]
}

export type ConfirmResult = PreflightConfirmResult | PreflightGateResult

/** Type guard: did confirm return the missing-key gate (vs. a started run)? */
export function isMissingKeysGate(r: ConfirmResult | null): r is PreflightGateResult {
  return !!r && (r as PreflightGateResult).status === 'missing_keys_gate'
}

// ---------------------------------------------------------------------------
// Mode catalog types
// ---------------------------------------------------------------------------

export interface ModeDialDefaults {
  speed: string
  capability: string
  resource: string
  depth: string
  hypothesis_count: string
}

export interface ModeEntry {
  id: string
  label: string
  description: string
  dial_defaults: ModeDialDefaults
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const DEBOUNCE_MS = 300

export function usePreflight() {
  const [estimate, setEstimate] = useState<PreflightResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modes, setModes] = useState<ModeEntry[]>([])
  const [modesLoading, setModesLoading] = useState(false)
  const [intents, setIntents] = useState<IntentEntry[]>([])
  const [userDefaults, setUserDefaults] = useState<UserDefaultEnvelope | null>(null)
  const [defaultsLoading, setDefaultsLoading] = useState(false)

  // Ref used to cancel in-flight debounced calls
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ---------------------------------------------------------------------------
  // Fetch per-user default envelope (once on mount)
  // ---------------------------------------------------------------------------

  const fetchUserDefaults = useCallback(async () => {
    setDefaultsLoading(true)
    try {
      const { data } = await api.get<{ envelope: UserDefaultEnvelope }>('/v3/user/defaults')
      if (data?.envelope && Object.keys(data.envelope).length > 0) {
        setUserDefaults(data.envelope)
      }
    } catch {
      // Non-fatal: fall back to hardcoded dial defaults
    } finally {
      setDefaultsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUserDefaults()
  }, [fetchUserDefaults])

  // ---------------------------------------------------------------------------
  // Fetch mode catalog (once on mount)
  // ---------------------------------------------------------------------------

  const fetchModes = useCallback(async () => {
    setModesLoading(true)
    try {
      const { data } = await api.get<ModeEntry[]>('/v3/preflight/modes')
      setModes(data)
    } catch {
      // Non-fatal: modes list stays empty; PreflightPanel falls back to inline mode labels
    } finally {
      setModesLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchModes()
  }, [fetchModes])

  // ---------------------------------------------------------------------------
  // Fetch intent catalog (once on mount) — populates the override dropdown
  // ---------------------------------------------------------------------------

  const fetchIntents = useCallback(async () => {
    try {
      const { data } = await api.get<IntentEntry[]>('/v3/preflight/intents')
      setIntents(data)
    } catch {
      // Non-fatal: dropdown falls back to current detected intent only
    }
  }, [])

  useEffect(() => {
    fetchIntents()
  }, [fetchIntents])

  // ---------------------------------------------------------------------------
  // Preflight estimate — immediate (used for initial load)
  // ---------------------------------------------------------------------------

  const preflight = useCallback(async (input: PreflightIn): Promise<PreflightResult | null> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data } = await api.post<PreflightResult>('/v3/preflight', input)
      setEstimate(data)
      return data
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      const msg = axiosErr?.response?.data?.detail ?? 'Preflight failed'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
      return null
    } finally {
      setIsLoading(false)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Debounced preflight — used when dials change to avoid hammering the API
  // ---------------------------------------------------------------------------

  const preflightDebounced = useCallback((input: PreflightIn): void => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current)
    }
    debounceTimer.current = setTimeout(() => {
      preflight(input)
    }, DEBOUNCE_MS)
  }, [preflight])

  // ---------------------------------------------------------------------------
  // Confirm — place wallet hold
  // ---------------------------------------------------------------------------

  const confirm = useCallback(async (input: PreflightConfirmIn): Promise<ConfirmResult | null> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data } = await api.post<ConfirmResult>('/v3/preflight/confirm', input)
      return data
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: { detail?: { error?: string; details?: string } | string } }
      }
      const detail = axiosErr?.response?.data?.detail
      if (typeof detail === 'object' && detail?.error) {
        setError(detail.error)
      } else {
        setError(typeof detail === 'string' ? detail : 'Confirm failed')
      }
      return null
    } finally {
      setIsLoading(false)
    }
  }, [])

  return {
    preflight,
    preflightDebounced,
    confirm,
    estimate,
    isLoading,
    error,
    modes,
    modesLoading,
    intents,
    userDefaults,
    defaultsLoading,
  }
}
