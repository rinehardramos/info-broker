import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import { getPipelineNodeEnabled, setPipelineNodeEnabled, getAppPluginEnabled, setAppPluginEnabled } from '../api/v3'
import { listNodeTypes, type NodeType } from '../api/pipelines'

// ─── Static integrations (non-pipeline-node plugins) ─────────────────────────

type HybridAppPlugin = {
  kind: 'hybrid_app'
  id: string
  title: string
  description: string
  tags: string[]
  route: string
}

const APP_PLUGINS: HybridAppPlugin[] = [
  {
    kind: 'hybrid_app',
    id: 'linkedin-scraper',
    title: 'LinkedIn Scraper',
    description: 'Harvest LinkedIn profiles using Apify actor runs. Configure targeting, run scraper jobs, view ingested profiles, and build automated pipelines.',
    tags: ['SRC'],
    route: '/linkedin',
  },
]

// ─── Category → tag mapping ──────────────────────────────────────────────────

const CATEGORY_TAG: Record<string, string> = {
  source: 'SRC',
  enrich: 'ENRICH',
  score: 'SCORE',
  filter: 'FILTER',
  datastore: 'DATASTORE',
}

const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  SRC:       { bg: '#1e3a5f', text: '#60a5fa' },
  ENRICH:    { bg: '#2d1f4e', text: '#a78bfa' },
  SCORE:     { bg: '#1a3a2a', text: '#4ade80' },
  PIPELINE:  { bg: '#1a2a1a', text: '#86efac' },
  FILTER:    { bg: '#3a2a1a', text: '#fb923c' },
  DATASTORE: { bg: '#3a1a2a', text: '#f472b6' },
}

function TagBadge({ tag }: { tag: string }) {
  const colors = TAG_COLORS[tag] ?? { bg: '#1e293b', text: '#94a3b8' }
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: '2px 6px',
        borderRadius: 4,
        background: colors.bg,
        color: colors.text,
        letterSpacing: '0.05em',
      }}
    >
      {tag}
    </span>
  )
}

// ─── Node descriptions (enriches the API data) ──────────────────────────────

const NODE_DESCRIPTIONS: Record<string, string> = {
  agent_input: 'Accept user query input. Used as the entry point for agent-triggered pipelines.',
  ddg_search: 'Search the web using DuckDuckGo. Enriches pipeline items with web search results for a given query.',
  qdrant_search: 'Enrich pipeline results with semantic vector search against your Qdrant collections.',
  rss_monitor: 'Fetch and parse RSS 2.0 and Atom feeds. Use as a source node to pull news or blog posts.',
  apify_actor: 'Run any Apify actor and ingest the resulting dataset as pipeline items.',
  ai_scoring: 'Score pipeline items using an LLM with configurable criteria and rubrics.',
  ai_provider: 'Call an LLM with a custom prompt. Use for enrichment, classification, or extraction.',
  manual_scoring: 'Extract a score field from item data. Use for rule-based scoring without LLM calls.',
  aggregator: 'Deduplicate and merge items from multiple upstream sources into a single stream.',
  obsidian_vault: 'Search your Obsidian vault via semantic vector search. Datastore for Intelligent Search.',
  local_files: 'Search local files by keyword. Supports glob patterns and path filters. Datastore for Intelligent Search.',
  web_crawl: 'Crawl websites with configurable depth and domain restrictions. Datastore for Intelligent Search.',
  intelligent_search: 'LLM-powered agentic research loop. Dynamically searches connected datastores and the web.',
  summarizer: 'Condense single or aggregated input items into a coherent, structured summary via LLM.',
}

// ─── Hybrid app plugin card ─────────────────────────────────────────────────

function HybridAppPluginCard({ plugin }: { plugin: HybridAppPlugin }) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ['app-plugin-enabled', plugin.id],
    queryFn: () => getAppPluginEnabled(plugin.id).catch(() => ({ plugin_id: plugin.id, enabled: true })),
  })

  const enabled = data?.enabled !== false

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => setAppPluginEnabled(plugin.id, next),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app-plugin-enabled', plugin.id] }),
  })

  return (
    <div
      onClick={() => enabled && navigate(plugin.route)}
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        opacity: enabled ? 1 : 0.55,
        transition: 'opacity 0.15s, border-color 0.15s',
        cursor: enabled ? 'pointer' : 'default',
      }}
      onMouseEnter={e => { if (enabled) e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{plugin.title}</span>
        <button
          onClick={e => { e.stopPropagation(); toggleMutation.mutate(!enabled) }}
          disabled={toggleMutation.isPending}
          style={{
            fontSize: 10, fontWeight: 600, padding: '3px 10px', borderRadius: 20,
            border: `1px solid ${enabled ? '#22c55e' : '#475569'}`,
            background: enabled ? '#14532d33' : 'transparent',
            color: enabled ? '#22c55e' : '#64748b',
            cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
          }}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {plugin.description}
      </p>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {plugin.tags.map(t => <TagBadge key={t} tag={t} />)}
        </div>
        {enabled && <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 600 }}>Open</span>}
      </div>
    </div>
  )
}

// ─── Node plugin card (dynamic from API) ────────────────────────────────────

function NodePluginCard({ node }: { node: NodeType }) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ['plugin-enabled', node.node_type],
    queryFn: () => getPipelineNodeEnabled(node.node_type).catch(() => ({ node_type: node.node_type, enabled: true })),
  })

  const enabled = data?.enabled !== false

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => setPipelineNodeEnabled(node.node_type, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plugin-enabled', node.node_type] })
      qc.invalidateQueries({ queryKey: ['nodeTypes'] })
    },
  })

  const tag = CATEGORY_TAG[node.category] ?? node.category.toUpperCase()
  const description = NODE_DESCRIPTIONS[node.node_type] ?? `${node.display_name} pipeline node.`

  return (
    <div
      onClick={() => navigate(`/plugins/node/${node.node_type}`)}
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        opacity: enabled ? 1 : 0.55,
        transition: 'opacity 0.15s, border-color 0.15s',
        cursor: 'pointer',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{node.display_name}</span>
        <button
          onClick={e => { e.stopPropagation(); toggleMutation.mutate(!enabled) }}
          disabled={toggleMutation.isPending}
          style={{
            fontSize: 10, fontWeight: 600, padding: '3px 10px', borderRadius: 20,
            border: `1px solid ${enabled ? '#22c55e' : '#475569'}`,
            background: enabled ? '#14532d33' : 'transparent',
            color: enabled ? '#22c55e' : '#64748b',
            cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
          }}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {description}
      </p>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <TagBadge tag={tag} />
        <TagBadge tag="PIPELINE" />
      </div>
    </div>
  )
}

// ─── Category sort order ────────────────────────────────────────────────────

const CATEGORY_ORDER = ['source', 'enrich', 'score', 'filter', 'datastore']

// ─── Page ───────────────────────────────────────────────────────────────────

export default function PluginsPage() {
  const { data: nodeTypes = [], isLoading } = useQuery({
    queryKey: ['all-node-types'],
    queryFn: listNodeTypes,
  })

  // Sort by category order, then alphabetically within category
  const sortedNodes = [...nodeTypes].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a.category)
    const bi = CATEGORY_ORDER.indexOf(b.category)
    const ao = ai === -1 ? 99 : ai
    const bo = bi === -1 ? 99 : bi
    if (ao !== bo) return ao - bo
    return a.display_name.localeCompare(b.display_name)
  })

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>Plugins</h1>
            <p style={{ fontSize: 11, color: 'var(--muted)', margin: '2px 0 0' }}>
              Integrations and pipeline nodes ({nodeTypes.length} available)
            </p>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto" style={{ padding: 20 }}>
          {/* App/Hybrid plugins */}
          <section style={{ marginBottom: 28 }}>
            <h2
              style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
                color: 'var(--muted)', margin: '0 0 12px',
              }}
            >
              INTEGRATIONS
            </h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 12,
              }}
            >
              {APP_PLUGINS.map(p => <HybridAppPluginCard key={p.id} plugin={p} />)}
            </div>
          </section>

          {/* Pipeline node plugins — fetched from API */}
          <section>
            <h2
              style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
                color: 'var(--muted)', margin: '0 0 12px',
              }}
            >
              PIPELINE NODES
            </h2>
            {isLoading ? (
              <p style={{ fontSize: 11, color: 'var(--muted)' }}>Loading nodes...</p>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: 12,
                }}
              >
                {sortedNodes.map(n => <NodePluginCard key={n.node_type} node={n} />)}
              </div>
            )}
          </section>
        </div>
      </div>
      <IconRail />
    </div>
  )
}
