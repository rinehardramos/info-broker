// frontend/src/types/gate.ts
//
// Types mirroring app/pipeline/strategist.py:GateResult / BrainSummary /
// UserQuestionPayload. See spec:
// docs/superpowers/specs/2026-05-22-gather-ask-user-diagnostic-design.md.

export interface BrainSummary {
  tool_calls: number
  findings: number
  hypothesis_count: number
  duration_ms: number
  invoked_tools: string[]
}

export interface GateResult {
  passed: boolean
  failing_check_kind: string | null
  failing_check_detail: Record<string, unknown>
  brain_summary: BrainSummary
}

export interface UserQuestionPayload {
  summary: string
  run_id: string
  phase_id: string
  // detail intentionally omitted from the WS-delivered shape; admin fetches
  // it via GET /v3/pipelines/runs/{run_id}/gate-detail.
}

export interface GateDetailResponse {
  run_id: string
  phase_id: string
  gate_result: GateResult | null
}
