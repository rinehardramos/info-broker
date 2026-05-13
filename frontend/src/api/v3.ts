import { api } from './client'

// --- Types ---

export interface UserOut {
  id: string
  username: string
  email: string | null
  is_active: boolean
  is_admin: boolean
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
  job_id: string | null
  session_id: string
  status: string
  reply: string | null
  mode: 'investigation' | 'conversational' | 'question'
  question?: string | null
  options?: string[] | null
}

export interface AgentSession {
  id: string
  genesis_query: string
  status: 'active' | 'archived'
  created_at: string
  turn_count: number
  run_count: number
  accumulated_summary: string
  entity_type: string
  conversation_thread?: Array<{ role: string; content: string; timestamp?: string }>
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

export const sendMessage = (
  message: string,
  sessionId?: string | null,
  useIntelligentSearch?: boolean,
  parentRunId?: string,
) =>
  api.post<AgentMessageOut>('/v3/agent/message', {
    message,
    session_id: sessionId ?? undefined,
    use_intelligent_search: useIntelligentSearch,
    parent_run_id: parentRunId,
  }).then(r => r.data)

export const archiveSession = (sessionId: string): Promise<void> =>
  api.post(`/v3/agent/sessions/${sessionId}/archive`).then(() => undefined)

export const listSessions = (): Promise<AgentSession[]> =>
  api.get('/v3/agent/sessions').then(r => r.data)

export const getSession = (sessionId: string): Promise<AgentSession> =>
  api.get(`/v3/agent/sessions/${sessionId}`).then(r => r.data)

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
  requires_key: string | null
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

export const runAnalyzer = (items: object[], analysisType?: string, contextPrompt?: string, query?: string, runId?: string) =>
  api.post('/v3/research-trails/analyze', { items, analysis_type: analysisType, context_prompt: contextPrompt, query, run_id: runId }).then(r => r.data)

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

// --- Exports ---

export const exportResearch = (runId: string, format: 'pdf' | 'csv' | 'xlsx') =>
  api.post<{ filename: string; url: string }>(`/v3/exports/research/${runId}`, { format, include_analysis: true }).then(r => r.data)

export type ExportFormat = 'csv' | 'xlsx'

export interface RunExport {
  id: string
  run_id: string
  format: ExportFormat
  status: 'pending' | 'ready' | 'failed'
  size_bytes: number | null
  error: string | null
  download_url: string | null
}

export const createExport = (runId: string, format: ExportFormat): Promise<RunExport> =>
  api.post<RunExport>(`/v3/exports/research/${runId}`, { format }).then(r => r.data)

export const getExport = (exportId: string): Promise<RunExport> =>
  api.get<RunExport>(`/v3/exports/${exportId}`).then(r => r.data)

// --- Scorecard ---

export async function getScorecard(runId: string): Promise<any> {
  try {
    const { data } = await api.get(`/v3/research-trails/${runId}/scorecard`)
    return data
  } catch {
    return null
  }
}

// --- Performance Dashboard ---

export interface TechniquePerf {
  tool: string
  avg_grade: string
  avg_numeric: number
  runs: number
  total_results: number
  errors: number
  error_rate: number
}

export interface TacticPerf {
  name: string
  avg_grade: string
  avg_numeric: number
  runs: number
  avg_yield: number
}

export interface PerformanceDashboardData {
  techniques: TechniquePerf[]
  tactics: TacticPerf[]
  total_runs: number
  error?: string
}

export const getPerformanceDashboard = (): Promise<PerformanceDashboardData> =>
  api.get<PerformanceDashboardData>('/v3/dashboard/technique-performance').then(r => r.data)

export async function backfillScorecards(): Promise<number> {
  try {
    const { data } = await api.post('/v3/research-trails/scorecards/backfill')
    return data?.count ?? 0
  } catch {
    return 0
  }
}

export async function submitScorecardGrade(
  runId: string,
  level: 'strategy' | 'tactic' | 'technique',
  name: string,
  grade: string,
): Promise<void> {
  await api.post(`/v3/research-trails/${runId}/scorecard/grade`, { level, name, grade })
}

// --- Metrics ---

export interface MetricsSummary {
  period_days: number
  runs: { total: number; succeeded: number; failed: number; budget_exhausted: number; success_rate: number }
  latency: { avg_seconds: number; p50_seconds: number; p95_seconds: number }
  steps: { node_type: string; total: number; succeeded: number; avg_items: number }[]
  strategies: { strategy: string; uses: number; avg_score: number }[]
}

export interface RunHistoryItem {
  id: string
  status: string
  trigger_type: string
  query: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  error_message: string | null
}

export const getMetricsSummary = (days = 30): Promise<MetricsSummary> =>
  api.get(`/v3/metrics/summary?days=${days}`).then(r => r.data)

export const getRunHistory = (limit = 50): Promise<RunHistoryItem[]> =>
  api.get(`/v3/metrics/runs?limit=${limit}`).then(r => r.data)

// --- Admin: User Management ---

export type UserRole = 'admin' | 'analyst' | 'viewer'

export interface UserRecord {
  id: string
  username: string
  email: string | null
  is_admin: boolean
  role: UserRole
  is_active: boolean
  org_id: string
  created_at: string
}

export const listUsers = (): Promise<UserRecord[]> =>
  api.get('/v3/auth/users').then(r => r.data)

export const patchUser = (
  userId: string,
  body: Partial<Pick<UserRecord, 'is_admin' | 'is_active' | 'role'>>,
): Promise<UserRecord> =>
  api.patch(`/v3/auth/users/${userId}`, body).then(r => r.data)

// --- Runs + dashboard metrics ---

export interface RunRow {
  id: string
  status: string
  query: string
  pipeline_name?: string | null
  trigger_type?: string | null
  created_at: string
  finished_at?: string | null
}

export interface RunMetrics {
  total_runs: number
  runs_today: number
  success_rate: number
  live_runs: number
  error_count: number
  avg_duration_seconds: number
}

export const listRuns = (): Promise<RunRow[]> =>
  api.get('/v3/agent/runs').then(r => r.data)

export const getRunMetrics = (): Promise<RunMetrics> =>
  api.get('/v3/metrics/summary').then(r => r.data)
