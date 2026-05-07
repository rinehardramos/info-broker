import { api } from './client'

// --- Types ---

export interface UserOut {
  id: string
  username: string
  email: string | null
  is_active: boolean
  created_at: string
}

export interface PreferencesOut {
  theme: string
  column_layout: Record<string, unknown>
  agent_pipeline_id: string | null
}

export interface JobOut {
  id: string
  status: string
  query: string
  created_at: string
  completed_at: string | null
  result_count: number
}

export interface MonitorOut {
  id: string
  name: string
  type: string
  target: string
  poll_interval_minutes: number
  last_polled_at: string | null
  last_item_count: number
  is_active: boolean
}

export interface PluginInfo {
  name: string
  description: string
  requires_api_key: boolean
  available: boolean
}

export interface CoreSettingsOut {
  settings: Record<string, string | null>
}

export interface AgentMessageOut {
  job_id: string
  status: string
}

export interface AgentPipelineOut {
  pipeline_id: string
  pipeline_name: string
  is_system: boolean
}

export interface JobResult {
  id: string
  source: string
  title: string
  url: string | null
  snippet: string | null
  created_at: string
  grade: string | null
}

// --- User ---

export const getMe = () => api.get<UserOut>('/v3/users/me').then(r => r.data)

export const getPreferences = () =>
  api.get<PreferencesOut>('/v3/users/me/preferences').then(r => r.data)

export const updatePreferences = (body: Partial<PreferencesOut>) =>
  api.put<PreferencesOut>('/v3/users/me/preferences', body).then(r => r.data)

// --- Agent ---

export const sendMessage = (message: string, context_job_id?: string, use_intelligent_search?: boolean, parent_run_id?: string) =>
  api.post<AgentMessageOut>('/v3/agent/message', { message, context_job_id, use_intelligent_search, parent_run_id }).then(r => r.data)

export const getAgentPipeline = (): Promise<AgentPipelineOut> =>
  api.get<AgentPipelineOut>('/v3/agent/pipeline').then(r => r.data)

export const setAgentPipeline = (pipeline_id: string): Promise<AgentPipelineOut> =>
  api.put<AgentPipelineOut>('/v3/agent/pipeline', { pipeline_id }).then(r => r.data)

export interface BrainStatus {
  ready: boolean
  auth_method: string
  logged_in: boolean
  has_api_key: boolean
  email?: string
  error?: string
}

export const getBrainStatus = (): Promise<BrainStatus> =>
  api.get<BrainStatus>('/v3/agent/brain/status').then(r => r.data)

// --- Jobs ---

export const listJobs = () => api.get<JobOut[]>('/v3/jobs').then(r => r.data)

export const getJob = (id: string) => api.get<JobOut>(`/v3/jobs/${id}`).then(r => r.data)

export const cancelJob = (id: string) => api.delete(`/v3/jobs/${id}`)

export async function getJobResults(jobId: string): Promise<JobResult[]> {
  const { data } = await api.get<JobResult[]>(`/v3/jobs/${jobId}/results`)
  return data
}

export async function gradeResult(jobId: string, resultId: string, grade: string): Promise<void> {
  await api.post(`/v3/jobs/${jobId}/results/${resultId}/grade`, { grade })
}

// --- Monitors ---

export const listMonitors = () => api.get<MonitorOut[]>('/v3/monitors').then(r => r.data)

export const createMonitor = (body: { name: string; type: string; target: string; poll_interval_minutes: number }) =>
  api.post<MonitorOut>('/v3/monitors', body).then(r => r.data)

export const deleteMonitor = (id: string) => api.delete(`/v3/monitors/${id}`)

// --- Plugins ---

export const listPlugins = () => api.get<PluginInfo[]>('/v3/plugins').then(r => r.data)

export const getPluginSchema = (name: string) =>
  api.get<Record<string, unknown>>(`/v3/plugins/${name}/schema`).then(r => r.data)

export const getPluginConfig = (name: string) =>
  api.get<{ plugin_name: string; config: Record<string, unknown> }>(`/v3/plugins/${name}/config`).then(r => r.data)

export const savePluginConfig = (name: string, config: Record<string, unknown>) =>
  api.put(`/v3/plugins/${name}/config`, { config }).then(r => r.data)

// --- Core settings ---

export const getCoreSettings = () =>
  api.get<CoreSettingsOut>('/v3/settings/core').then(r => r.data)

export const updateCoreSettings = (items: { key: string; value: string; is_secret?: boolean }[]) =>
  api.put<CoreSettingsOut>('/v3/settings/core', items).then(r => r.data)

export const getPipelineNodeEnabled = (
  nodeType: string,
): Promise<{ node_type: string; enabled: boolean }> =>
  api.get(`/v3/pipelines/nodes/types/${nodeType}/enabled`).then(r => r.data)

export const setPipelineNodeEnabled = (
  nodeType: string,
  enabled: boolean,
): Promise<void> =>
  api.put(`/v3/pipelines/nodes/types/${nodeType}/enabled`, { enabled }).then(() => undefined)

export const getAppPluginEnabled = (
  pluginId: string,
): Promise<{ plugin_id: string; enabled: boolean }> =>
  api.get(`/v3/settings/plugins/${pluginId}/enabled`).then(r => r.data)

export const setAppPluginEnabled = (
  pluginId: string,
  enabled: boolean,
): Promise<void> =>
  api.put(`/v3/settings/plugins/${pluginId}/enabled`, { enabled }).then(() => undefined)

// --- Node Health ---

export interface NodeHealthOut {
  node_type: string
  display_name: string
  healthy: boolean
  error: string | null
  requires_key: boolean
  setup_url: string | null
  setup_instructions: string | null
}

export const getNodeHealth = (): Promise<NodeHealthOut[]> =>
  api.get<NodeHealthOut[]>('/v3/pipelines/nodes/types/health').then(r => r.data)

// --- Research trail feedback ---

export const submitFindingFeedback = (runId: string, index: number, score: number, reason?: string, title?: string) =>
  api.post(`/v3/research-trails/${runId}/findings/${index}/feedback`, { score, reason, title }).then(r => r.data)

export const getRunFeedback = (runId: string): Promise<Record<string, { score: number; reason: string }>> =>
  api.get(`/v3/research-trails/${runId}/feedback`).then(r => r.data)

export const runAnalyzer = (items: object[], analysisType?: string, contextPrompt?: string, query?: string) =>
  api.post('/v3/research-trails/analyze', { items, analysis_type: analysisType, context_prompt: contextPrompt, query }).then(r => r.data)

// --- Knowledge Graph ---

export interface EntityOut {
  ref: string
  entity_type: string
  name: string
  confidence: number
  observation_count: number
  aliases?: string[]
  attributes?: Record<string, string>
  first_seen?: string
  last_seen?: string
}

export interface EntityObservation {
  attribute: string
  value: string
  confidence: number
  source_tool: string
  source_url: string | null
  observed_at: string
}

export interface KnowledgeStats {
  total_entities: number
  total_relationships: number
  entities_by_type: { entity_type: string; cnt: number }[]
  materializer_state: Record<string, unknown> | null
}

export const getEntityTypes = () =>
  api.get<{ name: string; display_name: string; icon: string }[]>('/v3/knowledge/entity-types').then(r => r.data)

export const searchEntities = (q: string, entityType?: string, limit = 50) =>
  api.get<EntityOut[]>('/v3/knowledge/entities', { params: { q, entity_type: entityType, limit } }).then(r => r.data)

export const getEntityDetail = (ref: string) =>
  api.get<{ entity: EntityOut; relationships: Record<string, unknown>[] }>(`/v3/knowledge/entities/${encodeURIComponent(ref)}`).then(r => r.data)

export const getEntityObservations = (ref: string) =>
  api.get<EntityObservation[]>(`/v3/knowledge/entities/${encodeURIComponent(ref)}/observations`).then(r => r.data)

export const getEntityGraph = (ref: string, hops = 2) =>
  api.get(`/v3/knowledge/entities/${encodeURIComponent(ref)}/graph`, { params: { hops } }).then(r => r.data)

export const getKnowledgeStats = () =>
  api.get<KnowledgeStats>('/v3/knowledge/stats').then(r => r.data)

export const getKnowledgeTimeline = (params?: { start?: string; end?: string; entity_ref?: string; limit?: number }) =>
  api.get<EntityObservation[]>('/v3/knowledge/timeline', { params }).then(r => r.data)

// --- Admin / Observability ---

export interface McpSession {
  id: string
  caller_identity: string
  session_type: string
  status: string
  tool_call_count: number
  context: Record<string, unknown>
  started_at: string
  finished_at: string | null
}

export interface McpToolCall {
  id: string
  tool_name: string
  node_type: string | null
  call_id: string
  parent_call_id: string | null
  status: string
  input_params: Record<string, unknown> | null
  result_preview: string | null
  result_count: number | null
  error_message: string | null
  duration_ms: number | null
  created_at: string
}

export interface DashboardMetrics {
  active_sessions: number
  total_tool_calls: number
  error_rate_last_hour: { errors: number; total: number }
  avg_duration_ms: number
  top_tools_24h: { tool_name: string; call_count: number; avg_ms: number }[]
}

export const listMcpSessions = (status?: string, limit = 50) =>
  api.get<McpSession[]>('/v3/admin/sessions', { params: { status, limit } }).then(r => r.data)

export const getMcpSession = (id: string) =>
  api.get<{ session: McpSession; calls: McpToolCall[] }>(`/v3/admin/sessions/${id}`).then(r => r.data)

export const getDashboardMetrics = () =>
  api.get<DashboardMetrics>('/v3/admin/dashboard').then(r => r.data)

export const getToolStats = () =>
  api.get<{ tool_name: string; total_calls: number; succeeded: number; failed: number; avg_duration_ms: number; last_used: string }[]>('/v3/admin/tools/stats').then(r => r.data)
