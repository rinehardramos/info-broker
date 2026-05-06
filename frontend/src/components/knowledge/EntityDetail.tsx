import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getEntityDetail, getEntityObservations, EntityObservation } from '../../api/v3'

interface Props {
  entityRef: string
}

type Tab = 'overview' | 'timeline'

export default function EntityDetail({ entityRef }: Props) {
  const [tab, setTab] = useState<Tab>('overview')

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: ['entity-detail', entityRef],
    queryFn: () => getEntityDetail(entityRef),
    enabled: !!entityRef,
  })

  const { data: observations, isLoading: loadingObs } = useQuery({
    queryKey: ['entity-observations', entityRef],
    queryFn: () => getEntityObservations(entityRef),
    enabled: !!entityRef && tab === 'timeline',
  })

  if (loadingDetail) {
    return (
      <div className="p-4 text-xs" style={{ color: 'var(--muted)' }}>
        Loading...
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="p-4 text-xs" style={{ color: 'var(--muted)' }}>
        Entity not found.
      </div>
    )
  }

  const { entity, relationships } = detail

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Entity header */}
      <div
        className="px-4 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-bold" style={{ color: 'var(--text)' }}>
            {entity.name}
          </span>
          <span
            className="text-[10px] px-1 rounded"
            style={{
              background: 'var(--surface)',
              color: 'var(--accent)',
              border: '1px solid var(--border)',
            }}
          >
            {entity.entity_type}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--muted)' }}>
          <span>{Math.round(entity.confidence * 100)}% confidence</span>
          <span>&middot;</span>
          <span>{entity.observation_count} observations</span>
        </div>
      </div>

      {/* Tab bar */}
      <div
        className="flex gap-0 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        {(['overview', 'timeline'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-4 py-2 text-xs capitalize"
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
              color: tab === t ? 'var(--accent)' : 'var(--muted)',
              cursor: 'pointer',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'overview' && (
          <OverviewTab relationships={relationships as Relationship[]} />
        )}
        {tab === 'timeline' && (
          <TimelineTab observations={observations ?? []} loading={loadingObs} />
        )}
      </div>
    </div>
  )
}

interface Relationship {
  relationship_type: string
  direction: string
  other_name: string
  other_type: string
  [key: string]: unknown
}

function OverviewTab({ relationships }: { relationships: Relationship[] }) {
  if (!relationships || relationships.length === 0) {
    return (
      <div className="p-4 text-xs" style={{ color: 'var(--muted)' }}>
        No relationships found.
      </div>
    )
  }

  return (
    <div className="p-4 flex flex-col gap-2">
      <div className="text-xs font-semibold mb-1" style={{ color: 'var(--muted)' }}>
        RELATIONSHIPS
      </div>
      {relationships.map((rel, i) => (
        <div
          key={i}
          className="flex items-center gap-2 px-3 py-2 rounded text-xs"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
          }}
        >
          <span
            className="px-1 rounded text-[10px]"
            style={{
              background: 'color-mix(in srgb, var(--accent) 15%, transparent)',
              color: 'var(--accent)',
            }}
          >
            {rel.relationship_type}
          </span>
          <span style={{ color: 'var(--muted)' }}>
            {rel.direction === 'outgoing' ? '→' : '←'}
          </span>
          <span style={{ color: 'var(--text)' }}>{rel.other_name}</span>
          <span
            className="ml-auto text-[10px] px-1 rounded"
            style={{
              background: 'var(--surface)',
              color: 'var(--muted)',
              border: '1px solid var(--border)',
            }}
          >
            {rel.other_type}
          </span>
        </div>
      ))}
    </div>
  )
}

function TimelineTab({
  observations,
  loading,
}: {
  observations: EntityObservation[]
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="p-4 text-xs" style={{ color: 'var(--muted)' }}>
        Loading...
      </div>
    )
  }

  if (observations.length === 0) {
    return (
      <div className="p-4 text-xs" style={{ color: 'var(--muted)' }}>
        No observations found.
      </div>
    )
  }

  const sorted = [...observations].sort(
    (a, b) => new Date(b.observed_at).getTime() - new Date(a.observed_at).getTime()
  )

  return (
    <div className="p-4 flex flex-col gap-2">
      {sorted.map((obs, i) => (
        <div
          key={i}
          className="flex flex-col gap-1 px-3 py-2 rounded text-xs"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
          }}
        >
          <div className="flex items-center gap-1">
            <span className="font-semibold" style={{ color: 'var(--text)' }}>
              {obs.attribute}
            </span>
            <span style={{ color: 'var(--muted)' }}>=</span>
            <span style={{ color: 'var(--accent)' }}>{obs.value}</span>
          </div>
          <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--muted)' }}>
            <span>{obs.source_tool}</span>
            <span>&middot;</span>
            <span>{Math.round(obs.confidence * 100)}%</span>
            <span>&middot;</span>
            <span>{new Date(obs.observed_at).toLocaleDateString()}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
