import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import MessageBubble from './MessageBubble'
import { sendMessage, getAgentPipeline } from '../../api/v3'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useSessionStore } from '../../stores/sessionStore'

interface Message {
  id: string
  role: 'user' | 'agent'
  content: string
  status?: string
}

let _msgCounter = 0

export default function AgentChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [sending, setSending]   = useState(false)
  const [useIntelligentSearch, setUseIntelligentSearch] = useState(false)
  const { activeJobId, setActiveJobId, setAgentInput } = useSessionStore()
  const bottomRef               = useRef<HTMLDivElement>(null)

  const { data: activePipeline } = useQuery({
    queryKey: ['agentPipeline'],
    queryFn: getAgentPipeline,
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useWebSocket((event: WsEvent) => {
    if (event.type === 'job.update' || event.type === 'job.completed' || event.type === 'job.failed') {
      setMessages(prev =>
        prev.map(m =>
          m.id === event.job_id
            ? { ...m, status: event.status }
            : m,
        ),
      )
      if (event.message && (event.type === 'job.completed' || event.type === 'job.failed')) {
        setMessages(prev => [
          ...prev,
          { id: `agent-${++_msgCounter}`, role: 'agent', content: event.message! },
        ])
      }
    }
    if (event.type === 'agent.message' && event.message) {
      setMessages(prev => [
        ...prev,
        { id: `agent-${++_msgCounter}`, role: 'agent', content: event.message! },
      ])
    }
  })

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setAgentInput(text)

    const userMsg: Message = { id: `user-${++_msgCounter}`, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])

    try {
      const result = await sendMessage(text, activeJobId ?? undefined, useIntelligentSearch)
      setMessages(prev => [
        ...prev,
        { id: result.job_id, role: 'agent', content: `Research started…`, status: 'pending' },
      ])
      setActiveJobId(result.job_id)
    } catch {
      setMessages(prev => [
        ...prev,
        { id: `err-${++_msgCounter}`, role: 'agent', content: 'Failed to start research. Check your connection.' },
      ])
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div
        className="px-3 py-2 text-[11px] font-semibold flex items-center justify-between"
        style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
      >
        <span>Agent</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {activePipeline && (
            <span
              style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 400 }}
              title="Active pipeline — change in Settings"
            >
              {activePipeline.pipeline_name}
              {activePipeline.is_system && (
                <span style={{ color: '#60a5fa', marginLeft: 3 }}>[Default]</span>
              )}
            </span>
          )}
          <button
            onClick={() => setUseIntelligentSearch(prev => !prev)}
            title={useIntelligentSearch ? 'Intelligent Search ON — click to disable' : 'Enable Intelligent Search'}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '2px 8px', borderRadius: 12, fontSize: 9, fontWeight: 600,
              border: `1px solid ${useIntelligentSearch ? '#a78bfa' : '#334155'}`,
              background: useIntelligentSearch ? '#a78bfa22' : 'transparent',
              color: useIntelligentSearch ? '#a78bfa' : '#64748b',
              cursor: 'pointer', transition: 'all 0.2s',
            }}
          >
            <span style={{ fontSize: 11 }}>{'\uD83D\uDD0D'}</span>
            IS
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>
            Ask anything — I'll research it for you.
          </p>
        )}
        {messages.map(m => (
          <MessageBubble key={m.id} role={m.role} content={m.content} status={m.status} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="px-3 py-2" style={{ borderTop: '1px solid var(--border)' }}>
        <textarea
          placeholder="Ask info-broker… (Enter to send)"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={sending}
          rows={2}
          className="w-full text-xs px-2 py-2 rounded resize-none outline-none disabled:opacity-50"
          style={{
            background: 'var(--panel2)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
        />
      </div>
    </div>
  )
}
