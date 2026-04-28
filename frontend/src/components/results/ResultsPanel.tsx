import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob, getJobResults } from '../../api/v3'
import NewsCard from './NewsCard'

type Tab = 'Profiles' | 'News' | 'Social' | 'Summary'
const TABS: Tab[] = ['Profiles', 'News', 'Social', 'Summary']

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('News')
  const col1Content = useSessionStore(s => s.col1Content)

  const { data: job } = useQuery({
    queryKey: ['job', col1Content?.jobId],
    queryFn: () => getJob(col1Content!.jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 3000 : false
    },
  })

  const { data: results = [] } = useQuery({
    queryKey: ['job-results', col1Content?.jobId],
    queryFn: () => getJobResults(col1Content!.jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId && job?.status === 'completed',
  })

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-3 gap-1 pt-2 pb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-2 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: activeTab === tab ? 'var(--panel2)' : 'transparent',
              color:      activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              border:     activeTab === tab ? '1px solid var(--border)' : '1px solid transparent',
              cursor: 'pointer',
            }}
          >
            {tab}
          </button>
        ))}
        {job && (
          <span className="ml-auto text-[10px] truncate max-w-[40%]" style={{ color: 'var(--subtext)' }}>
            {job.query}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {!col1Content && (
          <div className="text-center mt-16">
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              Send a message to the agent or tap a job in the live stream.
            </p>
          </div>
        )}

        {col1Content && activeTab === 'News' && (
          <div>
            {job && (
              <p className="text-[10px] mb-3" style={{ color: 'var(--subtext)' }}>
                {job.status === 'running' || job.status === 'pending'
                  ? '⟳ Research in progress…'
                  : `${job.status} — ${results.length} results`}
              </p>
            )}
            {results.map(r => (
              <NewsCard
                key={r.id}
                item={{
                  id: r.id,
                  title: r.title,
                  url: r.url ?? undefined,
                  snippet: r.snippet ?? undefined,
                  source_name: r.source,
                }}
              />
            ))}
            {job?.status === 'completed' && results.length === 0 && (
              <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>No results found.</p>
            )}
          </div>
        )}

        {col1Content && activeTab === 'Summary' && (
          <div className="text-xs p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            {job ? (
              <>
                <div className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>{job.query}</div>
                <div className="mb-1" style={{ color: 'var(--subtext)' }}>Status: {job.status}</div>
                <div style={{ color: 'var(--subtext)' }}>Results: {results.length}</div>
                {results.filter(r => r.source === 'qdrant').length > 0 && (
                  <div className="mt-2 text-[10px]" style={{ color: 'var(--muted)' }}>
                    {results.filter(r => r.source === 'qdrant').length} results from Qdrant memory
                  </div>
                )}
              </>
            ) : 'Loading…'}
          </div>
        )}

        {activeTab === 'Profiles' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Profile results appear here when LinkedIn plugin is active.</p>
        )}
        {activeTab === 'Social' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Social crawl results appear here.</p>
        )}
      </div>
    </div>
  )
}
