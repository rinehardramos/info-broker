import { useState } from 'react'
import { api } from '@/api/client'
import axios from 'axios'

export interface ShareLink {
  token: string
  share_url: string
  expires_at: string
}

export interface SharedRun {
  run_id: string
  query: string
  started_at: string | null
  completed_at: string | null
  status: string
  ranked_candidates: RankedCandidatePublic[]
  phases: PhasePublic[]
  shared_at: string | null
  expires_at: string
  expires_in_hours: number
}

export interface RankedCandidatePublic {
  name: string
  confidence: number
  signal_scores: Record<string, string>
  evidence: Array<{ source_class: string; source_url?: string; snippet: string; is_disconfirm?: boolean }>
  slot_idx: number
}

export interface PhasePublic {
  phase_id: string
  aggregated_findings: Array<{
    candidate_name: string
    source_class: string
    confidence: number
    evidence_summary: string
  }>
}

export function useShare(runId: string) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function createShareLink(ttlDays = 7): Promise<ShareLink | null> {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.post<ShareLink>(`/v3/runs/${runId}/share`, { ttl_days: ttlDays })
      return data
    } catch (err) {
      const msg = axios.isAxiosError(err)
        ? err.response?.data?.detail ?? err.message
        : 'Unknown error'
      setError(msg)
      return null
    } finally {
      setLoading(false)
    }
  }

  async function revokeShareLink(token: string): Promise<boolean> {
    setLoading(true)
    setError(null)
    try {
      await api.delete(`/v3/runs/${runId}/share/${token}`)
      return true
    } catch (err) {
      const msg = axios.isAxiosError(err)
        ? err.response?.data?.detail ?? err.message
        : 'Unknown error'
      setError(msg)
      return false
    } finally {
      setLoading(false)
    }
  }

  return { createShareLink, revokeShareLink, loading, error }
}

/** Fetch a shared run without authentication (public endpoint). */
export async function fetchSharedRun(token: string): Promise<SharedRun> {
  const { data } = await axios.get<SharedRun>(`/api/share/${token}`)
  return data
}
