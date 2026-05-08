import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import MessageBubble from './MessageBubble'
import { sendMessage, getAgentPipeline, getBrainStatus } from '../../api/v3'
import { api } from '../../api/client'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useSessionStore } from '../../stores/sessionStore'
import FileUploadZone, { type FileUploadZoneHandle } from '../chat/FileUploadZone'

interface Message {
  id: string
  role: 'user' | 'agent'
  content: string
  status?: string
  type?: 'message' | 'question' | 'plan'
  payload?: {
    question?: string
    options?: string[]
    plan?: Record<string, unknown>
    run_id?: string
    verification_status?: string
  }
}

let _msgCounter = 0

export default function AgentChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [sending, setSending]   = useState(false)
  const [useIntelligentSearch, setUseIntelligentSearch] = useState(false)
  const { activeJobId, setActiveJobId, setAgentInput } = useSessionStore()
  const bottomRef               = useRef<HTMLDivElement>(null)
  const uploadZoneRef           = useRef<FileUploadZoneHandle>(null)

  const { data: activePipeline } = useQuery({
    queryKey: ['agentPipeline'],
    queryFn: getAgentPipeline,
  })

  const { data: brainStatus } = useQuery({
    queryKey: ['brainStatus'],
    queryFn: getBrainStatus,
    refetchInterval: 60000,
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useWebSocket((event: WsEvent) => {
    if (event.type === 'job.update' || event.type === 'job.completed' || event.type === 'job.failed') {
      setMessages(prev =>
        prev.map(m =>
          m.id === event.job_id
            ? {
                ...m,
                status: event.status,
                ...(event.type === 'job.completed' && (event as WsEvent & { verification_status?: string }).verification_status
                  ? { payload: { ...m.payload, verification_status: (event as WsEvent & { verification_status?: string }).verification_status } }
                  : {}),
              }
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
    // Tool call streaming — update the running message with current tool
    if (event.type === 'is.tool_call' && event.job_id && event.status === 'calling') {
      const toolName = (event.tool ?? '').replace('mcp__info-broker-mcp__', '')
      setMessages(prev =>
        prev.map(m =>
          m.id === event.job_id
            ? { ...m, content: `Researching... ${toolName}` }
            : m,
        ),
      )
    }
    if (event.type === 'agent.message' && event.message) {
      setMessages(prev => [
        ...prev,
        { id: `agent-${++_msgCounter}`, role: 'agent', content: event.message! },
      ])
    }
    if (event.type === 'brain.question') {
      const qEvent = event as WsEvent & { question?: string; options?: string[] }
      setMessages(prev => [...prev, {
        id: `q-${Date.now()}`,
        role: 'agent',
        content: qEvent.question ?? '',
        type: 'question',
        payload: { question: qEvent.question, options: qEvent.options ?? [], run_id: event.run_id },
      }])
    }
    if (event.type === 'brain.plan') {
      const pEvent = event as WsEvent & { plan?: Record<string, unknown> }
      setMessages(prev => [...prev, {
        id: `plan-${Date.now()}`,
        role: 'agent',
        content: 'Research plan ready.',
        type: 'plan',
        payload: { plan: pEvent.plan, run_id: event.run_id },
      }])
    }
    if (event.type === 'source.indexed') {
      const sEvent = event as WsEvent & { source_id?: string; findings_count?: number }
      if (sEvent.source_id) {
        uploadZoneRef.current?.updateSource(sEvent.source_id, {
          status: 'indexed',
          findingsCount: sEvent.findings_count,
        })
      }
    }
    if (event.type === 'source.failed') {
      const sEvent = event as WsEvent & { source_id?: string }
      if (sEvent.source_id) {
        uploadZoneRef.current?.updateSource(sEvent.source_id, { status: 'failed' })
      }
    }
  })

  const [collapsedPlans, setCollapsedPlans] = useState<Record<string, boolean>>({})

  const handleBrainAnswer = async (runId: string, answer: string) => {
    await api.post('/v3/agent/brain-answer', { run_id: runId, answer })
    setMessages(prev => [...prev, {
      id: `a-${Date.now()}`,
      role: 'user',
      content: answer,
    }])
  }

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
            title={
              !brainStatus?.ready
                ? 'IS unavailable — Claude Code not authenticated'
                : useIntelligentSearch ? 'Intelligent Search ON — click to disable' : 'Enable Intelligent Search'
            }
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '2px 8px', borderRadius: 12, fontSize: 9, fontWeight: 600,
              border: `1px solid ${useIntelligentSearch ? '#a78bfa' : '#334155'}`,
              background: useIntelligentSearch ? '#a78bfa22' : 'transparent',
              color: useIntelligentSearch ? '#a78bfa' : '#64748b',
              cursor: 'pointer', transition: 'all 0.2s',
              position: 'relative',
            }}
          >
            <span style={{ fontSize: 11 }}>{'\uD83D\uDD0D'}</span>
            IS
            {/* Brain status indicator */}
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: brainStatus?.ready ? '#4ade80' : '#f87171',
              flexShrink: 0,
            }} title={brainStatus?.ready
              ? `Brain ready (${brainStatus.auth_method}${brainStatus.email ? ` — ${brainStatus.email}` : ''})`
              : brainStatus?.error ?? 'Not authenticated'
            } />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>
            Ask anything — I'll research it for you.
          </p>
        )}
        {messages.map(m => {
          // Question message — distinct styling with quick-reply options
          if (m.type === 'question') {
            const runId = m.payload?.run_id ?? ''
            const options = m.payload?.options ?? []
            return (
              <div key={m.id} style={{
                margin: '8px 0',
                padding: '10px 12px',
                borderLeft: '3px solid var(--accent)',
                background: 'var(--panel2)',
                borderRadius: '0 8px 8px 0',
              }}>
                <div style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 600, marginBottom: 4 }}>
                  ? Brain Question
                </div>
                <div style={{ fontSize: 12, color: 'var(--text)', marginBottom: 8 }}>
                  {m.content}
                </div>
                {options.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {options.map((opt: string, i: number) => (
                      <button
                        key={i}
                        onClick={() => handleBrainAnswer(runId, opt)}
                        style={{
                          padding: '6px 14px',
                          borderRadius: '16px',
                          border: '1px solid var(--accent)',
                          background: 'transparent',
                          color: 'var(--accent)',
                          cursor: 'pointer',
                          fontSize: '13px',
                          marginRight: '8px',
                          marginTop: '6px',
                        }}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          }

          // Plan message — collapsible card
          if (m.type === 'plan') {
            const plan = m.payload?.plan ?? {}
            const steps = (plan.steps as Record<string, unknown>[] | undefined) ?? []
            const isCollapsed = collapsedPlans[m.id] !== false // default collapsed
            return (
              <div key={m.id} style={{
                margin: '8px 0',
                border: '1px solid var(--border)',
                borderRadius: 8,
                background: 'var(--panel2)',
                overflow: 'hidden',
              }}>
                <button
                  onClick={() => setCollapsedPlans(prev => ({ ...prev, [m.id]: !isCollapsed }))}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--accent)',
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                >
                  <span>Research Plan</span>
                  <span style={{ fontSize: 10 }}>{isCollapsed ? '▶' : '▼'}</span>
                </button>
                {!isCollapsed && (
                  <div style={{ padding: '0 12px 10px', fontSize: 11, color: 'var(--text)' }}>
                    {steps.map((step: Record<string, unknown>, i: number) => (
                      <div key={i} style={{ marginBottom: 8, paddingTop: 6, borderTop: i > 0 ? '1px solid var(--border)' : 'none' }}>
                        <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 2 }}>
                          Step {i + 1} [{String(step.category ?? '')}]: {String(step.goal ?? '')}
                        </div>
                        {Array.isArray(step.tools) && step.tools.length > 0 && (
                          <div style={{ color: 'var(--muted)', marginBottom: 2 }}>
                            Tools: {(step.tools as string[]).join(', ')}
                          </div>
                        )}
                        {Array.isArray(step.completeness_criteria) && step.completeness_criteria.length > 0 && (
                          <ul style={{ margin: '2px 0 0 14px', padding: 0 }}>
                            {(step.completeness_criteria as string[]).map((c: string, j: number) => (
                              <li key={j} style={{ color: 'var(--muted)', listStyleType: 'disc' }}>{c}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                    {steps.length === 0 && (
                      <div style={{ color: 'var(--muted)', fontStyle: 'italic' }}>No steps defined.</div>
                    )}
                  </div>
                )}
              </div>
            )
          }

          // Regular message — pass through to MessageBubble, with optional verification badge
          const verificationStatus = m.payload?.verification_status
          return (
            <div key={m.id}>
              <MessageBubble role={m.role} content={m.content} status={m.status} />
              {verificationStatus && (
                <div style={{ textAlign: 'right', marginTop: -4, marginBottom: 4, paddingRight: 4 }}>
                  {verificationStatus === 'PASS' && (
                    <span style={{ fontSize: 10, color: '#4ade80', fontWeight: 600 }}>Verified</span>
                  )}
                  {verificationStatus === 'PASS_WITH_NOTES' && (
                    <span style={{ fontSize: 10, color: '#facc15', fontWeight: 600 }}>Verified (with notes)</span>
                  )}
                  {verificationStatus === 'BLOCKED' && (
                    <span style={{ fontSize: 10, color: '#f87171', fontWeight: 600 }}>Verification blocked</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      <div className="px-3 py-2" style={{ borderTop: '1px solid var(--border)' }}>
        <FileUploadZone ref={uploadZoneRef} />
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
