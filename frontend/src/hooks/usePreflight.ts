import { useState, useCallback } from 'react'
import { api } from '../api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DialsIn {
  capability: 'light' | 'general' | 'high'
  hypothesis_count: 'single' | 'paired' | 'competing' | 'adversarial' | 'swarm'
  depth: 'shallow' | 'search' | 'deep' | 'abyss'
}

export interface PreflightIn {
  query: string
  mode?: string
  dials?: Partial<DialsIn>
  strategy?: string
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
}

export interface PreflightConfirmResult {
  run_id: string
  hold_id: string
  held_ru: number
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function usePreflight() {
  const [estimate, setEstimate] = useState<PreflightResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const confirm = useCallback(async (input: PreflightConfirmIn): Promise<PreflightConfirmResult | null> => {
    setIsLoading(true)
    setError(null)
    try {
      const { data } = await api.post<PreflightConfirmResult>('/v3/preflight/confirm', input)
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

  return { preflight, confirm, estimate, isLoading, error }
}
