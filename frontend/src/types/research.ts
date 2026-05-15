export type PhaseStatus = 'pending' | 'running' | 'passed' | 'failed' | 'ask_user' | 'skipped'
export type GateStatus = 'pass' | 'fail' | 'ask_user'

export interface PhaseState {
  status: PhaseStatus
  n_tacticians: number
  distinct_candidate_names: string[]
  gate_status: GateStatus | null
}

export interface TacticianState {
  tactic_id: string
  forbidden_candidates: string[]
  candidate_names: string[]
  findings_count: number
  specialist_calls: number
}

export type SourceClass =
  | 'live_search'
  | 'prior_research'
  | 'training_knowledge'
  | 'primary_official'
  | 'primary_self'

export interface RankedCandidateEvidence {
  source_class: SourceClass
  source_url?: string
  snippet: string
  is_disconfirm?: boolean
}

export interface RankedCandidate {
  name: string
  confidence: number
  signal_scores: {
    primary?: 'match' | 'mismatch' | 'unknown'
    supporting?: 'match' | 'mismatch' | 'unknown'
    medium?: 'match' | 'mismatch' | 'unknown'
    recency?: 'match' | 'mismatch' | 'unknown'
  }
  evidence: RankedCandidateEvidence[]
  slot_idx: number
}
