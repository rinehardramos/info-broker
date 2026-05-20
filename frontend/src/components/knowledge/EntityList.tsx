import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchEntities, getEntityTypes, EntityOut } from '../../api/v3'
import { Skeleton } from '../ui/skeleton'

interface Props {
  onSelect: (ref: string) => void
  selectedRef: string | null
}

export default function EntityList({ onSelect, selectedRef }: Props) {
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(t)
  }, [query])

  const { data: entityTypes } = useQuery({
    queryKey: ['entity-types'],
    queryFn: getEntityTypes,
  })

  const { data: entities, isLoading } = useQuery({
    queryKey: ['entities', debouncedQuery, typeFilter],
    queryFn: () => searchEntities(debouncedQuery, typeFilter || undefined, 100),
  })

  const handleSelect = useCallback((ref: string) => {
    onSelect(ref)
  }, [onSelect])

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ borderRight: '1px solid var(--border)' }}
    >
      {/* Search controls */}
      <div
        className="flex flex-col gap-2 p-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <input
          type="text"
          placeholder="Search entities..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="px-2 py-1 rounded text-xs outline-none w-full"
          style={{
            background: 'var(--surface)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        />
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="px-2 py-1 rounded text-xs outline-none w-full"
          style={{
            background: 'var(--surface)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="">All types</option>
          {entityTypes?.map(t => (
            <option key={t.name} value={t.name}>
              {t.icon} {t.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* Entity list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-3 space-y-1.5" aria-busy="true">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        )}
        {!isLoading && (!entities || entities.length === 0) && (
          <div className="p-3 text-xs" style={{ color: 'var(--muted)' }}>
            No entities found.
          </div>
        )}
        {entities?.map((entity: EntityOut) => (
          <EntityCard
            key={entity.ref}
            entity={entity}
            selected={selectedRef === entity.ref}
            onSelect={handleSelect}
          />
        ))}
      </div>
    </div>
  )
}

function EntityCard({
  entity,
  selected,
  onSelect,
}: {
  entity: EntityOut
  selected: boolean
  onSelect: (ref: string) => void
}) {
  return (
    <button
      onClick={() => onSelect(entity.ref)}
      className="w-full text-left px-3 py-2 flex flex-col gap-1"
      style={{
        background: selected ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
        borderBottom: '1px solid var(--border)',
        borderLeft: selected ? '2px solid var(--accent)' : '2px solid transparent',
        cursor: 'pointer',
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className="text-xs font-bold truncate"
          style={{ color: selected ? 'var(--accent)' : 'var(--text)' }}
        >
          {entity.name}
        </span>
        <span
          className="text-[10px] px-1 rounded flex-shrink-0"
          style={{
            background: 'var(--surface)',
            color: 'var(--muted)',
            border: '1px solid var(--border)',
          }}
        >
          {entity.entity_type}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[10px]" style={{ color: 'var(--muted)' }}>
          {Math.round(entity.confidence * 100)}% confidence
        </span>
        <span className="text-[10px]" style={{ color: 'var(--muted)' }}>
          &middot; {entity.observation_count} obs
        </span>
      </div>
    </button>
  )
}
