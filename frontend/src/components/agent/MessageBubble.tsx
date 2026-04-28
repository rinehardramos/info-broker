interface Props {
  role: 'user' | 'agent'
  content: string
  status?: string
}

const statusColor: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  completed: '#4ade80',
  failed:    '#ef4444',
}

export default function MessageBubble({ role, content, status }: Props) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-2`}>
      <div
        className="max-w-[85%] px-3 py-2 rounded text-xs leading-relaxed"
        style={{
          background: isUser ? 'var(--accent)' : 'var(--panel2)',
          color:      isUser ? 'var(--bg)'     : 'var(--text)',
          border:     isUser ? 'none'           : '1px solid var(--border)',
        }}
      >
        {content}
        {status && (
          <span className="block mt-1 text-[10px]" style={{ color: statusColor[status] ?? 'var(--muted)' }}>
            ● {status}
          </span>
        )}
      </div>
    </div>
  )
}
