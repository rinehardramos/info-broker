import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import { getPipelineNodeEnabled, setPipelineNodeEnabled } from '../api/v3'

// ─── Static plugin registry ──────────────────────────────────────────────────

type AppPlugin = {
  kind: 'app'
  id: string
  title: string
  description: string
  tags: string[]
  route: string
}

type NodePlugin = {
  kind: 'node'
  id: string
  title: string
  description: string
  tags: string[]
  node_type: string
}

type PluginDef = AppPlugin | NodePlugin

const PLUGINS: PluginDef[] = [
  {
    kind: 'app',
    id: 'linkedin-scraper',
    title: 'LinkedIn Scraper',
    description: 'Harvest LinkedIn profiles using Apify actor runs. Configure targeting, run scraper jobs, view ingested profiles, and build automated pipelines.',
    tags: ['SRC'],
    route: '/linkedin',
  },
  {
    kind: 'node',
    id: 'ddg-search',
    title: 'DDG Search',
    description: 'Search the web using DuckDuckGo. Use as a source node in pipelines to pull search results for a given query.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'ddg_search',
  },
  {
    kind: 'node',
    id: 'qdrant-search',
    title: 'Qdrant Semantic Search',
    description: 'Enrich pipeline results with semantic vector search against your Qdrant collections.',
    tags: ['ENRICH', 'PIPELINE'],
    node_type: 'qdrant_search',
  },
  {
    kind: 'node',
    id: 'rss-monitor',
    title: 'RSS Monitor',
    description: 'Fetch and parse RSS 2.0 and Atom feeds. Use as a source node to pull news or blog posts into a pipeline.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'rss_monitor',
  },
  {
    kind: 'node',
    id: 'apify-actor',
    title: 'Apify Actor',
    description: 'Run any Apify actor and ingest the resulting dataset as pipeline items.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'apify_actor',
  },
]

// ─── Tag colors ───────────────────────────────────────────────────────────────

const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  SRC:      { bg: '#1e3a5f', text: '#60a5fa' },
  ENRICH:   { bg: '#2d1f4e', text: '#a78bfa' },
  SCORE:    { bg: '#1a3a2a', text: '#4ade80' },
  PIPELINE: { bg: '#1a2a1a', text: '#86efac' },
  FILTER:   { bg: '#3a2a1a', text: '#fb923c' },
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

// ─── Node plugin card (with enable/disable) ───────────────────────────────────

function NodePluginCard({ plugin }: { plugin: NodePlugin }) {
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ['plugin-enabled', plugin.node_type],
    queryFn: () => getPipelineNodeEnabled(plugin.node_type).catch(() => ({ node_type: plugin.node_type, enabled: true })),
  })

  const enabled = data?.enabled !== false

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => setPipelineNodeEnabled(plugin.node_type, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plugin-enabled', plugin.node_type] })
      qc.invalidateQueries({ queryKey: ['nodeTypes'] })
    },
  })

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        opacity: enabled ? 1 : 0.55,
        transition: 'opacity 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{plugin.title}</span>
        <button
          onClick={() => toggleMutation.mutate(!enabled)}
          disabled={toggleMutation.isPending}
          style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '3px 10px',
            borderRadius: 20,
            border: `1px solid ${enabled ? '#22c55e' : '#475569'}`,
            background: enabled ? '#14532d33' : 'transparent',
            color: enabled ? '#22c55e' : '#64748b',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {plugin.description}
      </p>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {plugin.tags.map(t => <TagBadge key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ─── App plugin card (navigates to full page) ─────────────────────────────────

function AppPluginCard({ plugin }: { plugin: AppPlugin }) {
  const navigate = useNavigate()

  return (
    <div
      onClick={() => navigate(plugin.route)}
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{plugin.title}</span>
        <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 600 }}>Open →</span>
      </div>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {plugin.description}
      </p>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {plugin.tags.map(t => <TagBadge key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PluginsPage() {
  const appPlugins = PLUGINS.filter((p): p is AppPlugin => p.kind === 'app')
  const nodePlugins = PLUGINS.filter((p): p is NodePlugin => p.kind === 'node')

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
              Curated integrations and pipeline nodes
            </p>
          </div>
          {/* Search stub — future feature */}
          <input
            disabled
            placeholder="Search plugins (coming soon)"
            style={{
              padding: '6px 12px',
              fontSize: 11,
              background: 'var(--panel)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--muted)',
              width: 220,
              cursor: 'not-allowed',
            }}
          />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto" style={{ padding: 20 }}>
          {/* App plugins */}
          <section style={{ marginBottom: 28 }}>
            <h2
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: 'var(--muted)',
                margin: '0 0 12px',
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
              {appPlugins.map(p => <AppPluginCard key={p.id} plugin={p} />)}
            </div>
          </section>

          {/* Pipeline node plugins */}
          <section>
            <h2
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: 'var(--muted)',
                margin: '0 0 12px',
              }}
            >
              PIPELINE NODES
            </h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 12,
              }}
            >
              {nodePlugins.map(p => <NodePluginCard key={p.id} plugin={p} />)}
            </div>
          </section>
        </div>
      </div>
      <IconRail />
    </div>
  )
}
