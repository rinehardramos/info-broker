import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob } from '../../api/v3'
import NewsCard from './NewsCard'
import ProfileCard from './ProfileCard'

type Tab = 'Profiles' | 'News' | 'Social' | 'Summary'
const TABS: Tab[] = ['Profiles', 'News', 'Social', 'Summary']

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('News')
  const col1Content               = useSessionStore(s => s.col1Content)

  const { data: job } = useQuery({
    queryKey: ['job', col1Content?.jobId],
    queryFn: () => getJob(col1Content!.jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId,
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
        {col1Content && (
          <span className="ml-auto text-[10px] truncate max-w-[40%]" style={{ color: 'var(--subtext)' }}>
            {job?.query ?? '…'}
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

        {col1Content?.type === 'job' && activeTab === 'News' && (
          <div>
            <p className="text-[10px] mb-3" style={{ color: 'var(--subtext)' }}>
              {job ? `Job ${job.status} — ${job.result_count} results` : 'Loading…'}
            </p>
            {job && job.result_count === 0 && (
              <NewsCard item={{
                id: 'placeholder',
                title: 'Research in progress',
                snippet: 'Results will appear here as the agent completes its research.',
              }} />
            )}
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'Summary' && (
          <div className="text-xs p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            {job ? (
              <>
                <div className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>{job.query}</div>
                <div style={{ color: 'var(--subtext)' }}>Status: {job.status}</div>
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

// Re-export for use in other contexts
export { ProfileCard, NewsCard }
