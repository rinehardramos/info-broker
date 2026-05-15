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
