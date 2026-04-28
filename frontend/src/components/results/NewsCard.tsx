interface NewsItem {
  id: string
  title: string
  url?: string
  snippet?: string
  source_name?: string
  published_at?: string
}

export default function NewsCard({ item }: { item: NewsItem }) {
  return (
    <div
      className="p-3 rounded mb-2 text-xs"
      style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
    >
      {item.url ? (
        <a href={item.url} target="_blank" rel="noopener noreferrer"
          className="font-semibold block mb-1 hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          {item.title}
        </a>
      ) : (
        <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{item.title}</div>
      )}
      {item.snippet && (
        <div className="line-clamp-2 mb-1" style={{ color: 'var(--subtext)' }}>{item.snippet}</div>
      )}
      <div className="flex gap-2" style={{ color: 'var(--muted)' }}>
        {item.source_name && <span>{item.source_name}</span>}
        {item.published_at && <span>{new Date(item.published_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}
