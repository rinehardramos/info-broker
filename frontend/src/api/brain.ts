const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000') as string

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const brainApi = {
  aggregate: (runId: string) =>
    post<{ summary: string }>('/v3/brain/aggregate', { run_id: runId }),

  report: (runId: string, format: 'md' | 'docx' = 'md') =>
    post<{ content: string; format: string }>('/v3/brain/report', { run_id: runId, format }),

  presentation: (runId: string) =>
    post<{ slides: unknown[] }>('/v3/brain/presentation', { run_id: runId }),

  saveAsPipeline: (runId: string, name: string) =>
    post<{ pipeline_id: string }>('/v3/brain/save-as-pipeline', { run_id: runId, name }),

  injectNode: (
    runId: string,
    opts: {
      node_spec?: Record<string, unknown>
      instruction?: string
      after_node_id?: string
    },
  ) =>
    post<{ node_id: string; status: 'queued' }>(`/v3/runs/${runId}/inject`, opts),
}
