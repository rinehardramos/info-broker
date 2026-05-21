import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCoreSettings, updateCoreSettings, getAgentPipeline, setAgentPipeline, getNodeHealth, NodeHealthOut } from '../api/v3'
import { listPipelines } from '../api/pipelines'
import { useForm } from 'react-hook-form'
import IconRail from '../components/layout/IconRail'
import { useSessionStore } from '../stores/sessionStore'
import AccountSection from '../components/settings/AccountSection'
import { api } from '../api/client'

const CORE_FIELDS = [
  // LLM Model Tiers
  { key: 'llm.reasoning_model',    label: 'Reasoning Model (Analysis, Orchestration)',  secret: false, hint: 'claude-opus-4-7' },
  { key: 'llm.general_model',      label: 'General Model (Scoring, Summarizing)',       secret: false, hint: 'claude-sonnet-4-6' },
  { key: 'anthropic_api_key',      label: 'Anthropic API Key (Claude)',                 secret: true },
  // Search engines (multi_search)
  { key: 'serper_api_key',         label: 'Serper API Key (Google Search)',             secret: true, hint: 'serper.dev — 2,500 free queries/mo' },
  { key: 'brave_api_key',          label: 'Brave Search API Key',                       secret: true, hint: 'brave.com/search/api — free tier available' },
  { key: 'exa_api_key',            label: 'Exa API Key (semantic web search)',          secret: true, hint: 'exa.ai — neural search engine' },
  { key: 'tavily_api_key',         label: 'Tavily API Key (AI-optimised search)',       secret: true, hint: 'tavily.com — 1,000 free queries/mo' },
  { key: 'yandex_api_key',         label: 'Yandex XML Search API Key',                  secret: true, hint: 'yandex.com/dev/xml — free 10,000/mo; without key falls back to HTML scrape' },
  { key: 'bing_api_key',           label: 'Bing Search API Key (Azure)',                secret: true, hint: 'azure.microsoft.com/bing-search — without key falls back to Yahoo HTML' },
  // LLM Providers
  { key: 'llm.active_provider',    label: 'Active LLM Provider',  secret: false },
  { key: 'openai_api_key',          label: 'OpenAI API Key',       secret: true },
  { key: 'gemini_api_key',          label: 'Gemini API Key',       secret: true },
  { key: 'llm.lmstudio.base_url',  label: 'LM Studio Base URL',   secret: false },
  // Infrastructure
  { key: 'db.postgres_url',        label: 'Postgres URL',         secret: false },
  { key: 'db.qdrant_host',         label: 'Qdrant Host',          secret: false },
  { key: 'rag.embedding_model',    label: 'Embedding Model',      secret: false },
  { key: 'jwt.secret',             label: 'JWT Secret',           secret: true },
  { key: 'jwt.expiry_hours',       label: 'JWT Expiry (hours)',    secret: false },
]

function CoreSettingsForm() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['core-settings'], queryFn: getCoreSettings })
  const { register, handleSubmit } = useForm()

  const save = useMutation({
    mutationFn: (values: Record<string, string>) =>
      updateCoreSettings(
        CORE_FIELDS
          .filter(f => values[f.key] !== undefined && values[f.key] !== '')
          .map(f => ({ key: f.key, value: values[f.key], is_secret: f.secret }))
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['core-settings'] }),
  })

  return (
    <form onSubmit={handleSubmit(v => save.mutate(v as Record<string, string>))} className="flex flex-col gap-3">
      {CORE_FIELDS.map(f => (
        <div key={f.key} className="flex flex-col gap-1">
          <label className="text-[11px]" style={{ color: 'var(--subtext)' }}>{f.label}</label>
          <input
            type={f.secret ? 'password' : 'text'}
            placeholder={data?.settings[f.key] ? String(data.settings[f.key]) : (f.secret ? '••••••••' : ((f as any).hint ?? ''))}
            {...register(f.key)}
            className="px-2 py-1 rounded text-xs outline-none"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={save.isPending}
        className="mt-2 px-4 py-2 rounded text-xs font-semibold w-fit disabled:opacity-50"
        style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
      >
        {save.isPending ? 'Saving…' : 'Save Core Settings'}
      </button>
      {save.isSuccess && <span className="text-xs" style={{ color: '#4ade80' }}>Saved</span>}
    </form>
  )
}

function PluginSettingsForm() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['core-settings'], queryFn: getCoreSettings })
  const [retention, setRetention] = useState(600)

  useEffect(() => {
    const v = data?.settings['live_panel.retention_seconds']
    if (v) setRetention(Number(v))
  }, [data])

  const save = useMutation({
    mutationFn: () =>
      updateCoreSettings([
        { key: 'live_panel.retention_seconds', value: String(retention), is_secret: false },
      ]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['core-settings'] }),
  })

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label className="text-[11px] mb-1 block" style={{ color: 'var(--subtext)' }}>
          LivePanel Retention (seconds)
        </label>
        <input
          type="number"
          min={60}
          max={86400}
          value={retention}
          onChange={e => setRetention(Number(e.target.value))}
          className="px-2 py-1 rounded text-xs outline-none"
          style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
        />
        <p className="text-[10px] mt-1" style={{ color: 'var(--muted)' }}>
          How long items stay visible in the Live panel. Default: 600s.
        </p>
      </div>
      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="px-4 py-2 rounded text-xs font-semibold w-fit disabled:opacity-50"
        style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
      >
        {save.isPending ? 'Saving…' : 'Save Plugin Settings'}
      </button>
      {save.isSuccess && <span className="text-xs" style={{ color: '#4ade80' }}>Saved</span>}
    </div>
  )
}

function AgentSettingsForm() {
  const qc = useQueryClient()
  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })
  const { data: activePipeline } = useQuery({ queryKey: ['agentPipeline'], queryFn: getAgentPipeline })

  const save = useMutation({
    mutationFn: (id: string) => setAgentPipeline(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agentPipeline'] }),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-[11px]" style={{ color: 'var(--subtext)' }}>
          Active Agent Pipeline
        </label>
        <select
          value={activePipeline?.pipeline_id ?? ''}
          onChange={e => save.mutate(e.target.value)}
          disabled={save.isPending}
          className="px-2 py-1 rounded text-xs outline-none"
          style={{
            background: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            cursor: 'pointer',
          }}
        >
          {pipelines.map(p => (
            <option key={p.id} value={p.id}>
              {p.name}{p.is_system ? ' [Default]' : ''}
            </option>
          ))}
        </select>
        <p className="text-[10px] mt-1" style={{ color: 'var(--muted)' }}>
          The pipeline used when you send a message in the Agent chat.
          Must have an Agent CLI source node.
        </p>
      </div>
      {save.isError && (
        <span className="text-[11px]" style={{ color: '#f87171' }}>
          {(save.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to save'}
        </span>
      )}
      {save.isSuccess && (
        <span className="text-[11px]" style={{ color: '#4ade80' }}>Saved</span>
      )}
    </div>
  )
}

const CATEGORY_ORDER = ['source', 'enrich', 'score', 'filter', 'datastore']

// Map requires_key env var names to core_settings DB keys
const KEY_TO_SETTING: Record<string, string> = {
  APIFY_API_TOKEN: 'apify_api_key',
  APOLLO_API_KEY: 'apollo_api_key',
  PROXYCURL_API_KEY: 'proxycurl_api_key',
  GEMINI_API_KEY: 'gemini_api_key',
  HUNTER_IO_API_KEY: 'hunter_io_api_key',
  SHODAN_API_KEY: 'shodan_api_key',
  CRUNCHBASE_API_KEY: 'crunchbase_api_key',
  WHOISXML_API_KEY: 'whoisxml_api_key',
}

function NodeHealthSection() {
  const { data: nodes = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['nodeHealth'],
    queryFn: getNodeHealth,
  })

  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [saveResult, setSaveResult] = useState<Record<string, 'ok' | 'error'>>({})

  const toggleExpanded = (nodeType: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(nodeType)) next.delete(nodeType)
      else next.add(nodeType)
      return next
    })
  }

  const byCategory: Record<string, NodeHealthOut[]> = {}
  for (const n of nodes) {
    // Infer category from node_type prefix heuristic if not present
    const cat = n.node_type.includes('enrich') ? 'enrich'
      : n.node_type.includes('score') ? 'score'
      : 'source'
    byCategory[cat] = byCategory[cat] ?? []
    byCategory[cat].push(n)
  }
  const orderedCategories = [
    ...CATEGORY_ORDER.filter(c => byCategory[c]),
    ...Object.keys(byCategory).filter(c => !CATEGORY_ORDER.includes(c)),
  ]

  const healthyCount = nodes.filter(n => n.healthy).length
  const totalCount = nodes.length

  if (isLoading) {
    return <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading node health…</p>
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-xs" style={{ color: '#f87171' }}>Failed to load node health</p>
        <button
          onClick={() => refetch()}
          className="px-3 py-1 rounded text-xs w-fit"
          style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)', cursor: 'pointer' }}
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[11px]" style={{ color: 'var(--subtext)' }}>
            {healthyCount} / {totalCount} nodes healthy
          </span>
          {totalCount - healthyCount > 0 && (
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded"
              style={{ background: '#ef444422', color: '#f87171', border: '1px solid #ef444433' }}
            >
              {totalCount - healthyCount} failing
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          className="text-[10px] px-2 py-1 rounded"
          style={{ background: 'var(--panel)', color: 'var(--muted)', border: '1px solid var(--border)', cursor: 'pointer' }}
        >
          Refresh
        </button>
      </div>

      {orderedCategories.map(cat => (
        <div key={cat}>
          <div
            className="text-[10px] font-semibold mb-2 px-1"
            style={{ color: 'var(--muted)', letterSpacing: '0.05em' }}
          >
            {cat.toUpperCase()}
          </div>
          <div className="flex flex-col gap-1">
            {byCategory[cat].map(node => {
              const expanded = expandedNodes.has(node.node_type)
              const hasDetails = !node.healthy && (node.error || node.setup_instructions || node.setup_url)

              return (
                <div
                  key={node.node_type}
                  className="rounded"
                  style={{
                    background: 'var(--panel)',
                    border: `1px solid ${node.healthy ? 'var(--border)' : '#ef444433'}`,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    className="flex items-center gap-2 px-3 py-2"
                    onClick={() => hasDetails && toggleExpanded(node.node_type)}
                    style={{ cursor: hasDetails ? 'pointer' : 'default' }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: node.healthy ? '#4ade80' : '#f87171',
                        flexShrink: 0,
                        display: 'inline-block',
                      }}
                    />
                    <span className="flex-1 text-xs" style={{ color: 'var(--text)' }}>
                      {node.display_name}
                    </span>
                    {node.healthy ? (
                      <span className="text-[10px]" style={{ color: '#4ade80' }}>Healthy</span>
                    ) : (
                      <span className="text-[10px]" style={{ color: '#f87171' }}>
                        {node.error ?? 'Unhealthy'}
                      </span>
                    )}
                    {hasDetails && (
                      <span className="text-[10px]" style={{ color: 'var(--muted)', marginLeft: 4 }}>
                        {expanded ? '▾' : '▸'}
                      </span>
                    )}
                  </div>

                  {expanded && hasDetails && (
                    <div
                      className="px-3 pb-3 flex flex-col gap-2"
                      style={{ borderTop: '1px solid var(--border)', paddingTop: 8 }}
                    >
                      {node.setup_instructions && (
                        <p className="text-[11px]" style={{ color: 'var(--subtext)', lineHeight: 1.5, whiteSpace: 'pre-line' }}>
                          {node.setup_instructions}
                        </p>
                      )}
                      {node.setup_url && !node.setup_url.startsWith('/') && (
                        <a
                          href={node.setup_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px]"
                          style={{ color: 'var(--accent)' }}
                        >
                          Get API key →
                        </a>
                      )}
                      {node.requires_key && KEY_TO_SETTING[node.requires_key] && (
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="password"
                            placeholder={`Paste ${node.requires_key}`}
                            value={keyInputs[node.requires_key] ?? ''}
                            onChange={e => setKeyInputs(prev => ({ ...prev, [node.requires_key!]: e.target.value }))}
                            className="flex-1 text-[11px] px-2 py-1 rounded"
                            style={{
                              background: 'var(--bg)',
                              color: 'var(--text)',
                              border: '1px solid var(--border)',
                              outline: 'none',
                            }}
                          />
                          <button
                            disabled={!keyInputs[node.requires_key] || saving === node.requires_key}
                            onClick={async () => {
                              const envKey = node.requires_key!
                              const settingKey = KEY_TO_SETTING[envKey]
                              const val = keyInputs[envKey]
                              if (!settingKey || !val) return
                              setSaving(envKey)
                              try {
                                await updateCoreSettings([{ key: settingKey, value: val, is_secret: true }])
                                setSaveResult(prev => ({ ...prev, [envKey]: 'ok' }))
                                setKeyInputs(prev => ({ ...prev, [envKey]: '' }))
                                // Refresh health after saving
                                setTimeout(() => refetch(), 1000)
                              } catch {
                                setSaveResult(prev => ({ ...prev, [envKey]: 'error' }))
                              } finally {
                                setSaving(null)
                              }
                            }}
                            className="text-[10px] px-3 py-1 rounded"
                            style={{
                              background: saving === node.requires_key ? 'var(--panel2)' : 'var(--accent)',
                              color: 'var(--bg)',
                              border: 'none',
                              cursor: keyInputs[node.requires_key] ? 'pointer' : 'not-allowed',
                              opacity: keyInputs[node.requires_key] ? 1 : 0.5,
                            }}
                          >
                            {saving === node.requires_key ? '...' : 'Save'}
                          </button>
                          {saveResult[node.requires_key] === 'ok' && (
                            <span className="text-[10px]" style={{ color: '#4ade80' }}>Saved</span>
                          )}
                          {saveResult[node.requires_key] === 'error' && (
                            <span className="text-[10px]" style={{ color: '#f87171' }}>Failed</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

type DefaultModeState = {
  resolved: string
  source: 'org' | 'global' | 'fallback'
  org_value: string | null
  global_value: string | null
}

type ModeEntry = { id: string; label: string; description?: string }

function DefaultModeForm() {
  const isAdmin = useSessionStore(s => s.isAdmin)
  const role = useSessionStore(s => s.role)
  const isOrgAdmin = role === 'admin'

  const [modes, setModes] = useState<ModeEntry[]>([])
  const [state, setState] = useState<DefaultModeState | null>(null)
  const [saving, setSaving] = useState<'global' | 'org' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get('/v3/preflight/modes'),
      api.get('/v3/settings/default_mode'),
    ])
      .then(([modesResp, defResp]) => {
        setModes(modesResp.data as ModeEntry[])
        setState(defResp.data as DefaultModeState)
      })
      .catch(e => setError(e?.response?.data?.detail || 'Failed to load'))
  }, [])

  async function save(scope: 'global' | 'org', value: string | null) {
    setSaving(scope)
    setError(null)
    try {
      const resp = await api.put('/v3/settings/default_mode', { value, scope })
      setState(resp.data as DefaultModeState)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(null)
    }
  }

  if (error) return <div style={{ color: 'var(--danger)' }}>{error}</div>
  if (!state) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  const labelFor = (id: string) => modes.find(m => m.id === id)?.label || id

  return (
    <div className="space-y-6">
      {isAdmin && (
        <section>
          <div className="text-xs font-semibold mb-2" style={{ color: 'var(--text)' }}>
            System default
          </div>
          <select
            disabled={saving === 'global'}
            value={state.global_value ?? ''}
            onChange={e => save('global', e.target.value || null)}
            className="text-xs px-2 py-1 rounded"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          >
            <option value="">— not set (uses fallback: investigation) —</option>
            {modes.map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted)' }}>
            Applies to every org that has not set its own override.
          </div>
        </section>
      )}

      {isOrgAdmin && (
        <section>
          <div className="text-xs font-semibold mb-2" style={{ color: 'var(--text)' }}>
            Org default
          </div>
          <select
            disabled={saving === 'org'}
            value={state.org_value ?? ''}
            onChange={e => save('org', e.target.value || null)}
            className="text-xs px-2 py-1 rounded"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          >
            <option value="">Use system default ({labelFor(state.global_value || 'investigation')})</option>
            {modes.map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted)' }}>
            {state.org_value
              ? 'Active for everyone in this org.'
              : `Inherited from system default: ${labelFor(state.global_value || 'investigation')}.`}
          </div>
        </section>
      )}

      <div className="text-[11px] pt-2" style={{ color: 'var(--muted)', borderTop: '1px solid var(--border)' }}>
        Currently resolved for you: <b>{labelFor(state.resolved)}</b> (source: {state.source})
      </div>
    </div>
  )
}

export default function Settings() {
  const isAdmin = useSessionStore(s => s.isAdmin)
  const role = useSessionStore(s => s.role)
  const canSeeDefaultMode = isAdmin || role === 'admin'
  const [section, setSection] = useState<'core' | 'plugins' | 'agent' | 'node-health' | 'account' | 'default-mode'>(
    isAdmin ? 'core' : 'account',
  )

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex h-full flex-1 overflow-hidden">
        <div className="w-40 flex-shrink-0 col-scroll py-3 px-2" style={{ background: 'var(--panel)', borderRight: '1px solid var(--border)' }}>
          <div className="text-[10px] font-semibold mb-2 px-1" style={{ color: 'var(--muted)' }}>ACCOUNT</div>
          <button
            onClick={() => setSection('account')}
            className="w-full text-left px-2 py-1 rounded text-xs mb-1"
            style={{
              background: section === 'account' ? 'var(--panel2)' : 'transparent',
              color: section === 'account' ? 'var(--accent)' : 'var(--text)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Account
          </button>
          {canSeeDefaultMode && (
            <button
              onClick={() => setSection('default-mode')}
              className="w-full text-left px-2 py-1 rounded text-xs mb-1"
              style={{
                background: section === 'default-mode' ? 'var(--panel2)' : 'transparent',
                color: section === 'default-mode' ? 'var(--accent)' : 'var(--text)',
                border: 'none', cursor: 'pointer',
              }}
            >
              Default Mode
            </button>
          )}

          {isAdmin && (
            <>
              <div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>SYSTEM</div>
              <button
                onClick={() => setSection('core')}
                className="w-full text-left px-2 py-1 rounded text-xs mb-1"
                style={{
                  background: section === 'core' ? 'var(--panel2)' : 'transparent',
                  color: section === 'core' ? 'var(--accent)' : 'var(--text)',
                  border: 'none', cursor: 'pointer',
                }}
              >
                Core Settings
              </button>
            </>
          )}

          {isAdmin && (
            <>
              <div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>PLUGINS</div>
              <button
                onClick={() => setSection('plugins')}
                className="w-full text-left px-2 py-1 rounded text-xs mb-1"
                style={{
                  background: section === 'plugins' ? 'var(--panel2)' : 'transparent',
                  color: section === 'plugins' ? 'var(--accent)' : 'var(--text)',
                  border: 'none', cursor: 'pointer',
                }}
              >
                General
              </button>
            </>
          )}

          <div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>AGENT</div>
          <button
            onClick={() => setSection('agent')}
            className="w-full text-left px-2 py-1 rounded text-xs mb-1"
            style={{
              background: section === 'agent' ? 'var(--panel2)' : 'transparent',
              color: section === 'agent' ? 'var(--accent)' : 'var(--text)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Agent
          </button>

          <div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>NODES</div>
          <button
            onClick={() => setSection('node-health')}
            className="w-full text-left px-2 py-1 rounded text-xs mb-1"
            style={{
              background: section === 'node-health' ? 'var(--panel2)' : 'transparent',
              color: section === 'node-health' ? 'var(--accent)' : 'var(--text)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Node Health
          </button>
        </div>

        <div className="flex-1 col-scroll p-4">
          <h2 className="text-sm font-bold mb-4 capitalize" style={{ color: 'var(--accent)' }}>
            {section === 'account' ? 'Account'
              : section === 'core' ? 'Core Settings'
              : section === 'agent' ? 'Agent Settings'
              : section === 'node-health' ? 'Node Health'
              : section === 'default-mode' ? 'Default Mode'
              : 'Plugin Settings'}
          </h2>
          {section === 'account' && <AccountSection />}
          {isAdmin && section === 'core' && <CoreSettingsForm />}
          {isAdmin && section === 'plugins' && <PluginSettingsForm />}
          {section === 'agent' && <AgentSettingsForm />}
          {section === 'node-health' && <NodeHealthSection />}
          {section === 'default-mode' && <DefaultModeForm />}
        </div>
      </div>
      <IconRail />
    </div>
  )
}
