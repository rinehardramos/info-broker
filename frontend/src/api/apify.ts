import { api } from './client'

export interface ApifyRunConfig {
  job_titles: string[]
  locations: string[]
  max_items: number
  scraper_mode: string
  auto_query_segmentation: boolean
  auto_query_segmentation_levels: string[]
  auto_query_segmentation_countries: string[]
  recently_changed_jobs: boolean
  recently_posted_on_linkedin: boolean
}

export interface ApifyConfigOut {
  api_key: string | null
  actor_id: string | null
  run_config: ApifyRunConfig
}

export interface ApifyConfigIn {
  api_key?: string | null
  actor_id?: string | null
  job_titles?: string[]
  locations?: string[]
  max_items?: number
  scraper_mode?: string
  auto_query_segmentation?: boolean
  auto_query_segmentation_levels?: string[]
  auto_query_segmentation_countries?: string[]
  recently_changed_jobs?: boolean
  recently_posted_on_linkedin?: boolean
}

export interface ApifyRunOut {
  id: string
  apify_run_id: string | null
  status: string
  item_count: number
  started_at: string
  finished_at: string | null
}

export interface ApifyRunStatusOut {
  status: string
  item_count: number
  apify_run_id: string | null
}

export interface ApifyRunIn {
  job_titles: string[]
  locations: string[]
  max_items: number
  scraper_mode: string
  auto_query_segmentation: boolean
  auto_query_segmentation_levels: string[]
  auto_query_segmentation_countries: string[]
  recently_changed_jobs: boolean
  recently_posted_on_linkedin: boolean
}

export const getApifyConfig = (): Promise<ApifyConfigOut> =>
  api.get('/v3/apify/config').then((r) => r.data)

export const saveApifyConfig = (body: ApifyConfigIn): Promise<ApifyConfigOut> =>
  api.post('/v3/apify/config', body).then((r) => r.data)

export const startApifyRun = (): Promise<ApifyRunOut> =>
  api.post('/v3/apify/run').then((r) => r.data)

export const listApifyRuns = (): Promise<ApifyRunOut[]> =>
  api.get('/v3/apify/runs').then((r) => r.data)

export const getApifyRunStatus = (runId: string): Promise<ApifyRunStatusOut> =>
  api.get(`/v3/apify/runs/${runId}/status`).then((r) => r.data)

export interface LinkedInProfile {
  id: string
  first_name: string | null
  last_name: string | null
  headline: string | null
  about: string | null
}

export const listLinkedInProfiles = (limit = 50, offset = 0): Promise<LinkedInProfile[]> =>
  api.get('/v3/apify/profiles', { params: { limit, offset } }).then((r) => r.data)
