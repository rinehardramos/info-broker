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

export const sendMessage = (message: string, context_job_id?: string) =>
  api.post<AgentMessageOut>('/v3/agent/message', { message, context_job_id }).then(r => r.data)

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
