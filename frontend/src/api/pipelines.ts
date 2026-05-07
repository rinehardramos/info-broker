import { api } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PipelineNodeIn {
  id?: string                      // frontend UUID — sent to backend to use as DB node ID
  node_type: string
  label: string
  config: Record<string, unknown>
  position_x?: number
  position_y?: number
}

export interface PipelineNodeOut extends PipelineNodeIn {
  id: string
  category: string
}

export interface PipelineEdgeIn {
  source_node_id: string
  target_node_id: string
  edge_type?: string
}

export interface PipelineEdgeOut extends PipelineEdgeIn {
  id: string
}

export interface PipelineIn {
  name: string
  description?: string | null
  nodes?: PipelineNodeIn[]
  edges?: PipelineEdgeIn[]
}

export interface Pipeline {
  id: string
  name: string
  description: string | null
  is_system: boolean
  created_at: string
  updated_at: string
}

export interface PipelineDetail extends Pipeline {
  nodes: PipelineNodeOut[]
  edges: PipelineEdgeOut[]
}

export interface PipelineStepRun {
  id: string
  node_id: string
  status: string
  item_count: number
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface PipelineRun {
  id: string
  pipeline_id: string
  status: string
  trigger_type: string
  started_at: string
  finished_at: string | null
  error_message?: string | null
  query?: string | null
}

export interface ResearchFinding {
  source?: string
  title?: string
  content?: string
  url?: string
  confidence?: number
  branch?: string
  depth?: number
}

export interface ResearchTrail {
  query: string
  entity_type: string | null
  findings: ResearchFinding[]
  trail: {
    total_branches?: number
    resolved?: number
    dead_ends?: number
    needs_tool?: number
    max_depth_reached?: number
    can_go_deeper?: boolean
    deeper_leads?: string[]
    branches?: Array<{
      name: string
      status: string
      depth: number
      findings_count: number
      tools_used: string[]
      reason?: string
    }>
  }
  tool_calls: number
  suggested_pipeline?: {
    name: string
    nodes: Array<{ node_type: string; label: string; config: Record<string, unknown> }>
    edges: Array<{ source_index: number; target_index: number }>
  } | null
  analysis?: Record<string, unknown> | null
}

export interface PipelineRunDetail extends PipelineRun {
  steps: PipelineStepRun[]
  research?: ResearchTrail | null
}

export interface NodeType {
  node_type: string
  display_name: string
  category: string
  config_schema: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const createPipeline = (body: PipelineIn): Promise<Pipeline> =>
  api.post('/v3/pipelines', body).then(r => r.data)

export const listPipelines = (): Promise<Pipeline[]> =>
  api.get('/v3/pipelines').then(r => r.data)

export const getPipeline = (id: string): Promise<PipelineDetail> =>
  api.get(`/v3/pipelines/${id}`).then(r => r.data)

export const updatePipeline = (id: string, body: PipelineIn): Promise<Pipeline> =>
  api.put(`/v3/pipelines/${id}`, body).then(r => r.data)

export const deletePipeline = (id: string): Promise<void> =>
  api.delete(`/v3/pipelines/${id}`).then(() => undefined)

export const startPipelineRun = (id: string, variables?: Record<string, string>): Promise<PipelineRun> =>
  api.post(`/v3/pipelines/${id}/run`, { variables: variables ?? {} }).then(r => r.data)

export const listPipelineRuns = (id: string): Promise<PipelineRun[]> =>
  api.get(`/v3/pipelines/${id}/runs`).then(r => r.data)

export const getPipelineRun = (runId: string): Promise<PipelineRunDetail> =>
  api.get(`/v3/pipelines/runs/${runId}`).then(r => r.data)

export const listNodeTypes = (): Promise<NodeType[]> =>
  api.get('/v3/pipelines/nodes/types').then(r => r.data)

export interface PipelineRunSummary {
  id: string
  pipeline_id: string
  pipeline_name: string
  status: string
  trigger_type: string
  started_at: string
  finished_at: string | null
  step_count: number
  steps_done: number
  error_message: string | null
  query: string | null
}

export const listAllPipelineRuns = (): Promise<PipelineRunSummary[]> =>
  api.get('/v3/pipelines/runs/all').then(r => r.data)

export const cancelPipelineRun = (runId: string): Promise<void> =>
  api.post(`/v3/pipelines/runs/${runId}/cancel`).then(() => undefined)

export interface PluginRequest {
  id: string
  spec: { name: string; description: string; reason: string }
  status: string
  created_at: string
  reviewed_at: string | null
}

export const listPluginRequests = (): Promise<PluginRequest[]> =>
  api.get('/v3/pipelines/plugin-requests').then(r => r.data)

export const updatePluginRequestStatus = (id: string, status: string): Promise<void> =>
  api.put(`/v3/pipelines/plugin-requests/${id}/status`, { status }).then(() => undefined)
