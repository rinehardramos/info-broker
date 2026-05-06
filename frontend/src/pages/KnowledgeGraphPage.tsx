import { useState } from 'react'
import IconRail from '../components/layout/IconRail'
import EntityList from '../components/knowledge/EntityList'
import EntityDetail from '../components/knowledge/EntityDetail'

export default function KnowledgeGraphPage() {
  const [selectedRef, setSelectedRef] = useState<string | null>(null)

  return (
    <div
      className="flex h-screen"
      style={{ background: 'var(--bg)', color: 'var(--text)' }}
    >
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Page header */}
        <div
          className="px-4 py-3 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <h1 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            Knowledge Graph
          </h1>
        </div>

        {/* Split panel */}
        <div className="flex flex-1 overflow-hidden">
          {/* Entity list — 1/3 */}
          <div className="w-1/3 overflow-hidden">
            <EntityList
              onSelect={ref => setSelectedRef(ref)}
              selectedRef={selectedRef}
            />
          </div>

          {/* Entity detail — 2/3 */}
          <div className="flex-1 overflow-hidden">
            {selectedRef ? (
              <EntityDetail entityRef={selectedRef} />
            ) : (
              <div
                className="flex h-full items-center justify-center text-xs"
                style={{ color: 'var(--muted)' }}
              >
                Select an entity to view details
              </div>
            )}
          </div>
        </div>
      </div>

      <IconRail />
    </div>
  )
}
