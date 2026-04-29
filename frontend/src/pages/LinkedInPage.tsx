import { useState, useEffect } from 'react'
import { PipelineBuilder } from '../components/pipeline/PipelineBuilder'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import TagInput from '../components/linkedin/TagInput'
import {
  getApifyConfig,
  saveApifyConfig,
  startApifyRun,
  listApifyRuns,
  getApifyRunStatus,
  listLinkedInProfiles,
  gradeLinkedInProfile,
  type ApifyRunOut,
  type LinkedInProfile,
} from '../api/apify'
import GradeBar from '../components/results/GradeBar'

const inputStyle: React.CSSProperties = {
  background: 'var(--panel)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
}

const STATUS_COLORS: Record<string, string> = {
  queued: '#94a3b8',
  running: '#facc15',
  ingesting: '#60a5fa',
  succeeded: '#4ade80',
  failed: '#f87171',
  ingest_failed: '#f87171',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
      style={{ background: STATUS_COLORS[status] ?? '#6b7280', color: '#000' }}
    >
      {status}
    </span>
  )
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div
        onClick={() => onChange(!checked)}
        style={{
          width: 32, height: 18, borderRadius: 9,
          background: checked ? 'var(--accent)' : 'var(--border)',
          position: 'relative', transition: 'background 0.2s', flexShrink: 0,
          cursor: 'pointer',
        }}
      >
        <div style={{
          position: 'absolute', top: 2, left: checked ? 14 : 2,
          width: 14, height: 14, borderRadius: '50%',
          background: '#fff', transition: 'left 0.2s',
        }} />
      </div>
      <span className="text-xs" style={{ color: 'var(--text)' }}>{label}</span>
    </label>
  )
}

function RunRow({ run }: { run: ApifyRunOut }) {
  const qc = useQueryClient()
  const terminal = ['succeeded', 'failed', 'ingest_failed']
  const isLive = !terminal.includes(run.status)

  useQuery({
    queryKey: ['apify-run-status', run.id],
    queryFn: () => getApifyRunStatus(run.id),
    enabled: isLive,
    refetchInterval: (query) => (terminal.includes(query.state.data?.status ?? '') ? false : 4000),
    select: (data) => {
      if (data.status !== run.status) {
        qc.invalidateQueries({ queryKey: ['apify-runs'] })
      }
      return data
    },
  })

  return (
    <div
      className="flex items-center justify-between text-xs px-3 py-2 rounded mb-2"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      <div className="flex flex-col gap-0.5">
        <span style={{ color: 'var(--muted)', fontSize: 10 }}>
          {new Date(run.started_at).toLocaleString()}
        </span>
        {run.finished_at && (
          <span style={{ color: 'var(--muted)', fontSize: 10 }}>
            finished {new Date(run.finished_at).toLocaleString()}
          </span>
        )}
        {run.item_count > 0 && (
          <span style={{ color: 'var(--subtext)' }}>{run.item_count} profiles</span>
        )}
      </div>
      <StatusBadge status={run.status} />
    </div>
  )
}

function ProfileCard({ p }: { p: LinkedInProfile }) {
  const name = [p.first_name, p.last_name].filter(Boolean).join(' ') || '—'
  return (
    <div className="p-3 rounded mb-2 text-xs" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
      <div className="font-semibold mb-0.5" style={{ color: 'var(--text)' }}>{name}</div>
      {p.headline && <div className="mb-1 truncate" style={{ color: 'var(--subtext)' }}>{p.headline}</div>}
      {p.about && <div className="line-clamp-3" style={{ color: 'var(--muted)' }}>{p.about}</div>}
      <GradeBar
        resultId={p.id}
        jobId=""
        initialGrade={p.grade}
        onGrade={(profileId, grade) => { gradeLinkedInProfile(profileId, grade).catch(() => {}) }}
      />
    </div>
  )
}

function RightPanel({ runs, runsLoading }: { runs: ApifyRunOut[]; runsLoading: boolean }) {
  const [tab, setTab] = useState<'profiles' | 'runs' | 'pipelines'>('profiles')

  const { data: profiles = [], isLoading: profilesLoading } = useQuery({
    queryKey: ['linkedin-profiles'],
    queryFn: () => listLinkedInProfiles(100),
    refetchInterval: tab === 'profiles' ? 10000 : false,
  })

  const tabBtn = (label: string, key: 'profiles' | 'runs' | 'pipelines') => (
    <button
      onClick={() => setTab(key)}
      className="px-2 py-1 rounded text-[11px] font-medium"
      style={{
        background: tab === key ? 'var(--panel2)' : 'transparent',
        color: tab === key ? 'var(--accent)' : 'var(--muted)',
        border: tab === key ? '1px solid var(--border)' : '1px solid transparent',
        cursor: 'pointer',
      }}
    >
      {label}{key === 'profiles' && profiles.length > 0 ? ` (${profiles.length})` : ''}
    </button>
  )

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center gap-1 px-3 pt-2 pb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {tabBtn('Profiles', 'profiles')}
        {tabBtn('Run History', 'runs')}
        {tabBtn('Pipelines', 'pipelines')}
      </div>
      {tab === 'pipelines' && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <PipelineBuilder />
        </div>
      )}
      <div className="flex-1 col-scroll p-3" style={{ display: tab === 'pipelines' ? 'none' : undefined }}>
        {tab === 'profiles' && (
          <>
            {profilesLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading…</p>}
            {!profilesLoading && profiles.length === 0 && (
              <p className="text-xs" style={{ color: 'var(--muted)' }}>No profiles yet. Click Run Scraper to ingest data.</p>
            )}
            {profiles.map((p) => <ProfileCard key={p.id} p={p} />)}
          </>
        )}
        {tab === 'runs' && (
          <>
            {runsLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading…</p>}
            {!runsLoading && runs.length === 0 && (
              <p className="text-xs" style={{ color: 'var(--muted)' }}>No runs yet.</p>
            )}
            {runs.map((run) => <RunRow key={run.id} run={run} />)}
          </>
        )}
      </div>
    </div>
  )
}

export default function LinkedInPage() {
  const qc = useQueryClient()

  const { data: config } = useQuery({ queryKey: ['apify-config'], queryFn: getApifyConfig })
  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: ['apify-runs'],
    queryFn: listApifyRuns,
    refetchInterval: 10000,
  })

  const [apiKey, setApiKey] = useState('')
  const [actorId, setActorId] = useState('')
  const [jobTitles, setJobTitles] = useState<string[]>([])
  const [locations, setLocations] = useState<string[]>([])
  const [maxItems, setMaxItems] = useState(300)
  const [scraperMode, setScraperMode] = useState('Full + email search')
  const [autoQuerySeg, setAutoQuerySeg] = useState(false)
  const [segLevels, setSegLevels] = useState<string[]>(['country', 'industry', 'seniority_level'])
  const [segCountries, setSegCountries] = useState<string[]>([])
  const [recentlyChanged, setRecentlyChanged] = useState(false)
  const [recentlyPosted, setRecentlyPosted] = useState(false)

  useEffect(() => {
    if (!config) return
    if (config.actor_id) setActorId(config.actor_id)
    const rc = config.run_config
    setJobTitles(rc.job_titles)
    setLocations(rc.locations)
    setMaxItems(rc.max_items)
    setScraperMode(rc.scraper_mode)
    setAutoQuerySeg(rc.auto_query_segmentation)
    setSegLevels(rc.auto_query_segmentation_levels)
    setSegCountries(rc.auto_query_segmentation_countries)
    setRecentlyChanged(rc.recently_changed_jobs)
    setRecentlyPosted(rc.recently_posted_on_linkedin)
  }, [config])

  const saveConfig = useMutation({
    mutationFn: () =>
      saveApifyConfig({
        api_key: apiKey || null,
        actor_id: actorId || null,
        job_titles: jobTitles,
        locations,
        max_items: maxItems,
        scraper_mode: scraperMode,
        auto_query_segmentation: autoQuerySeg,
        auto_query_segmentation_levels: segLevels,
        auto_query_segmentation_countries: segCountries,
        recently_changed_jobs: recentlyChanged,
        recently_posted_on_linkedin: recentlyPosted,
      }),
    onSuccess: () => {
      setApiKey('')
      qc.invalidateQueries({ queryKey: ['apify-config'] })
    },
  })

  const startRun = useMutation({
    mutationFn: () => startApifyRun(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['apify-runs'] }),
  })

  const canRun = !!config?.api_key && !!config?.actor_id

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        {/* Left column: config */}
        <div className="w-80 flex-shrink-0 col-scroll p-4" style={{ borderRight: '1px solid var(--border)' }}>
          <h2 className="text-sm font-bold mb-4" style={{ color: 'var(--accent)' }}>LinkedIn Harvester</h2>

          <div className="flex flex-col gap-3">
            {/* Credentials */}
            <div className="text-[10px] font-semibold" style={{ color: 'var(--muted)' }}>CREDENTIALS</div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: 'var(--muted)' }}>
                Apify API Key {config?.api_key && <span style={{ color: '#4ade80' }}>✓ set</span>}
              </label>
              <input
                type="password"
                placeholder={config?.api_key ? '••••••••' : 'Enter API key…'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              />
            </div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: 'var(--muted)' }}>Actor ID</label>
              <input
                type="text"
                placeholder="e.g. myorg~linkedin-scraper"
                value={actorId}
                onChange={(e) => setActorId(e.target.value)}
                className="w-full px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              />
            </div>

            {/* Targeting */}
            <div className="text-[10px] font-semibold mt-1" style={{ color: 'var(--muted)' }}>TARGETING</div>

            <TagInput label="Job Titles" tags={jobTitles} onChange={setJobTitles} placeholder="CEO, CTO…" />
            <TagInput label="Locations" tags={locations} onChange={setLocations} placeholder="United States…" />

            <div>
              <label className="text-xs mb-1 block" style={{ color: 'var(--muted)' }}>Max Items</label>
              <input
                type="number"
                min={1}
                max={1000}
                value={maxItems}
                onChange={(e) => setMaxItems(Number(e.target.value))}
                className="w-full px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              />
            </div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: 'var(--muted)' }}>Scraper Mode</label>
              <select
                value={scraperMode}
                onChange={(e) => setScraperMode(e.target.value)}
                className="w-full px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              >
                <option>Full + email search</option>
                <option>Full</option>
                <option>Lite</option>
              </select>
            </div>

            {/* Filters */}
            <div className="text-[10px] font-semibold mt-1" style={{ color: 'var(--muted)' }}>FILTERS</div>

            <Toggle label="Recently Changed Jobs" checked={recentlyChanged} onChange={setRecentlyChanged} />
            <Toggle label="Recently Posted on LinkedIn" checked={recentlyPosted} onChange={setRecentlyPosted} />

            {/* Auto-segmentation */}
            <div className="text-[10px] font-semibold mt-1" style={{ color: 'var(--muted)' }}>AUTO-SEGMENTATION</div>

            <Toggle label="Enable Auto Query Segmentation" checked={autoQuerySeg} onChange={setAutoQuerySeg} />
            <TagInput
              label="Segmentation Levels"
              tags={segLevels}
              onChange={setSegLevels}
              placeholder="country, industry, seniority_level…"
            />
            <TagInput
              label="Target Countries (codes)"
              tags={segCountries}
              onChange={setSegCountries}
              placeholder="US, GB, AU…"
            />

            {/* Actions */}
            <div className="flex flex-col gap-2 mt-2">
              <button
                type="button"
                onClick={() => saveConfig.mutate()}
                disabled={saveConfig.isPending}
                className="px-3 py-1.5 rounded text-xs font-semibold disabled:opacity-50"
                style={{ background: 'var(--panel2)', color: 'var(--text)', border: '1px solid var(--border)', cursor: 'pointer' }}
              >
                {saveConfig.isPending ? 'Saving…' : 'Save Config'}
              </button>
              {saveConfig.isSuccess && <span className="text-xs" style={{ color: '#4ade80' }}>Config saved</span>}
              {saveConfig.isError && <span className="text-xs" style={{ color: '#f87171' }}>Save failed</span>}

              <button
                type="button"
                onClick={() => startRun.mutate()}
                disabled={!canRun || startRun.isPending}
                className="px-3 py-1.5 rounded text-xs font-semibold disabled:opacity-50"
                style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
              >
                {startRun.isPending ? 'Starting…' : 'Run Scraper'}
              </button>
              {startRun.isError && (
                <span className="text-xs" style={{ color: '#f87171' }}>
                  {(startRun.error as Error)?.message ?? 'Start failed'}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right column: tabbed results */}
        <RightPanel runs={runs} runsLoading={runsLoading} />
      </div>
      <IconRail />
    </div>
  )
}
