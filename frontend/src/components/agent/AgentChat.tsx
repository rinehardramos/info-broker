import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import MessageBubble from './MessageBubble'
import { sendMessage, getBrainStatus, archiveSession } from '../../api/v3'
import type { AgentMessageOut } from '../../api/v3'
import { api } from '../../api/client'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useSessionStore } from '../../stores/sessionStore'
import { useChatStore, type Message } from '../../stores/chatStore'
import FileUploadZone, { type FileUploadZoneHandle } from '../chat/FileUploadZone'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { brainApi } from '@/api/brain'
import { cn } from '@/lib/utils'
import { BrainSuggestionBanner } from '@/components/results/BrainSuggestionBanner'
import { PreflightPanel } from '@/components/preflight'

let _msgCounter = 0

export default function AgentChat() {
  const chatMessages = useChatStore(s => s.messages)
  const clearMessages = useChatStore(s => s.clearMessages)
  const sessionId = useChatStore(s => s.sessionId)
  const setSessionId = useChatStore(s => s.setSessionId)
  const setGenesisQuery = useChatStore(s => s.setGenesisQuery)
  const pushSessionRun = useChatStore(s => s.pushSessionRun)
  const setChatMessages = useChatStore(s => s.setMessages)
  // Wrap setMessages to support functional updater pattern (prev => newArr)
  const setMessages = (updater: Message[] | ((prev: Message[]) => Message[])) => {
    if (typeof updater === 'function') {
      setChatMessages(updater(useChatStore.getState().messages))
    } else {
      setChatMessages(updater)
    }
  }
  const messages = chatMessages
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput]       = useState(() => searchParams.get('q') ?? '')
  const [sending, setSending]   = useState(false)
  const [useIntelligentSearch, setUseIntelligentSearch] = useState(true)
  // All queries go through preflight + three-tier brain. Legacy path removed
  // since we're pre-production and want every run to surface the new flow.
  const [preflightQuery, setPreflightQuery] = useState<string | null>(null)

  // Clear ?q= from URL after pre-filling input so back-navigation doesn't re-fill
  useEffect(() => {
    if (searchParams.get('q')) setSearchParams({}, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  // Replay support: ?replay=<run_id> seeds runStreamStore from research_trails
  // so past runs render their cards / candidate comparison / ACH matrix / source
  // class badges without needing a fresh execution.
  useEffect(() => {
    const replayRunId = searchParams.get('replay')
    if (!replayRunId) return
    void import('@/hooks/useReplay').then(mod => {
      void mod.replayRunIntoStore(replayRunId).then((ok) => {
        if (ok) {
          // Use the statically-imported useSessionStore (top of file) to avoid
          // a dynamic-import race window that could fire after the user has
          // navigated away.
          const s = useSessionStore.getState()
          s.setActiveJobId(replayRunId)
          // setCol1Content triggers ResultsPanel auto-switch to this run tab
          s.setCol1Content({ type: 'pipeline_run', runId: replayRunId })
        }
      })
    })
    const next = new URLSearchParams(searchParams)
    next.delete('replay')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  // run_ids that have a brain.question in flight — skip "Researching…" for these
  const pendingQuestionsRef = useRef<Set<string>>(new Set())
  const { activeJobId, setActiveJobId, setAgentInput } = useSessionStore()
  const hasActiveRun = useRunStreamStore(
    (s) => !!activeJobId && s.runsById[activeJobId]?.status === 'running'
  )
  const bottomRef               = useRef<HTMLDivElement>(null)
  const uploadZoneRef           = useRef<FileUploadZoneHandle>(null)

  const { data: brainStatus } = useQuery({
    queryKey: ['brainStatus'],
    queryFn: getBrainStatus,
    refetchInterval: 60000,
  })

  // Poll for held confirmations — catches events missed due to WS disconnect / page refresh
  useQuery({
    queryKey: ['pendingConfirmations'],
    queryFn: async () => {
      const r = await api.get<{ pending: Array<{ run_id: string; candidate: string; candidate_desc: string; confidence: number; alternatives: string[] }> }>('/v3/agent/confirm/pending')
      for (const p of r.data.pending ?? []) {
        // Only add if not already in messages
        setMessages(prev => {
          const alreadyShown = prev.some(m => m.type === 'confirm' && m.payload?.run_id === p.run_id)
          if (alreadyShown) return prev
          return [...prev, {
            id: `confirm-${p.run_id}`,
            role: 'agent' as const,
            content: p.candidate,
            type: 'confirm',
            payload: { candidate: p.candidate, candidate_desc: p.candidate_desc, confidence: p.confidence, alternatives: p.alternatives, run_id: p.run_id },
          }]
        })
      }
      return r.data
    },
    refetchInterval: 15000,
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
                status: event.status as Message['status'],
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
      // Track that this run has a question — prevents "Researching…" from being added later
      if (event.run_id) pendingQuestionsRef.current.add(event.run_id)
      setMessages(prev => {
        // Remove the "Researching…" optimistic placeholder for this run (handles non-race case)
        const filtered = event.run_id
          ? prev.filter(m => m.id !== event.run_id)
          : prev
        return [...filtered, {
          id: `q-${Date.now()}`,
          role: 'agent',
          content: qEvent.question ?? '',
          type: 'question',
          payload: { question: qEvent.question, options: qEvent.options ?? [], run_id: event.run_id },
        }]
      })
    }
    if (event.type === 'brain.confirm') {
      const cEvent = event as WsEvent & {
        candidate?: string; candidate_desc?: string
        confidence?: number; alternatives?: string[]
      }
      setMessages(prev => [...prev, {
        id: `confirm-${Date.now()}`,
        role: 'agent',
        content: cEvent.candidate ?? '',
        type: 'confirm',
        payload: {
          candidate: cEvent.candidate,
          candidate_desc: cEvent.candidate_desc,
          confidence: cEvent.confidence,
          alternatives: cEvent.alternatives ?? [],
          run_id: event.run_id,
        },
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

  const [pirGoal, setPirGoal] = useState('')
  const [showPir, setShowPir] = useState(false)
  const [collapsedPlans, setCollapsedPlans] = useState<Record<string, boolean>>({})
  // Track which questions have been answered (msgId → answer text)
  const [answeredQuestions, setAnsweredQuestions] = useState<Record<string, string>>({})
  // Track custom answer input per question
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({})

  const handleEndSession = async () => {
    if (sessionId) {
      try { await archiveSession(sessionId) } catch { /* non-fatal */ }
    }
    clearMessages()
    setPirGoal('')
    setShowPir(false)
  }

  const handleBrainAnswer = async (runId: string, answer: string, msgId: string) => {
    setAnsweredQuestions(prev => ({ ...prev, [msgId]: answer }))
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

    // Every query goes through preflight first. Set the query and return —
    // PreflightPanel handles mode/dial selection and confirm-to-run.
    if (!preflightQuery) {
      setPreflightQuery(text)
      setInput('')
      return
    }

    // Change 2: route to node injection when the currently focused run is active
    const activeJobId = useSessionStore.getState().activeJobId
    const activeRunId = activeJobId && useRunStreamStore.getState().runsById[activeJobId]?.status === 'running'
      ? activeJobId
      : null

    if (activeRunId && text) {
      void brainApi.injectNode(activeRunId, { instruction: text })
      useChatStore.getState().addMessage({
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        status: 'done',
      })
      setInput('')
      return
    }

    setInput('')
    setSending(true)
    setAgentInput(text)

    const messageToSend = pirGoal.trim()
      ? `[RESEARCH GOAL: ${pirGoal.trim()}]\n\n${text}`
      : text

    const userMsg: Message = { id: `user-${++_msgCounter}`, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])

    try {
      const result: AgentMessageOut = await sendMessage(
        messageToSend,
        sessionId ?? undefined,
        useIntelligentSearch,
      )

      // Store session_id from first response
      if (result.session_id) {
        setSessionId(result.session_id)
        if (!sessionId) setGenesisQuery(text)  // first message = genesis
      }

      if (result.mode === 'conversational' && result.reply) {
        // Conversational reply — render directly, no spinner, no ResultsPanel tab
        setMessages(prev => [
          ...prev,
          { id: `agent-${++_msgCounter}`, role: 'agent', content: result.reply! },
        ])
      } else if (result.mode === 'question' && result.question) {
        // PreFlight clarification — render the question inline from HTTP response
        // This is reliable vs WS (WS delivery is best-effort / belt+suspenders)
        setMessages(prev => [
          ...prev,
          {
            id: `q-${Date.now()}`,
            role: 'agent',
            content: result.question!,
            type: 'question',
            payload: { question: result.question, options: result.options ?? [], run_id: result.job_id },
          },
        ])
        // Don't add "Researching…" and don't push a session run tab yet
      } else {
        // Investigation — existing async flow
        // Only add "Researching…" if brain.question hasn't already arrived for this run
        if (!pendingQuestionsRef.current.has(result.job_id!)) {
          setMessages(prev => [
            ...prev,
            { id: result.job_id!, role: 'agent', content: `Researching…`, status: 'pending' },
          ])
        }
        pendingQuestionsRef.current.delete(result.job_id!)
        setActiveJobId(result.job_id!)
        pushSessionRun(result.job_id!)
        // Always switch the results panel to the new run's tab so the flow graph shows.
        const { setCol1Content } = useSessionStore.getState()
        setCol1Content({ type: 'pipeline_run', runId: result.job_id! })
      }
    } catch (err: unknown) {
      // Extract HTTP error detail from axios error if available
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      const status = axiosErr?.response?.status
      const detail = axiosErr?.response?.data?.detail

      let errorContent: string
      if (status === 402) {
        errorContent = detail ?? 'Insufficient credits. Please top up your account to run research.'
      } else if (status && detail) {
        errorContent = `Error ${status}: ${detail}`
      } else if (status) {
        errorContent = `Request failed (HTTP ${status}). Check your connection.`
      } else {
        errorContent = 'Failed to start research. Check your connection.'
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `err-${++_msgCounter}`,
          role: 'agent' as const,
          content: errorContent,
          status: 'error' as const,
        },
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

  // Preflight panel — always shown after query submission, before the run starts
  if (preflightQuery) {
    return (
      <div className="flex flex-col h-full" style={{ padding: 16 }}>
        <PreflightPanel
          query={preflightQuery}
          onCancel={() => {
            setPreflightQuery(null)
            // Restore the query to the input so the user can edit and resubmit.
            setInput(preflightQuery)
          }}
          onConfirmed={(runId, _holdId) => {
            // POST /v3/preflight/confirm with start_run=true ALREADY launched
            // engine_v2 in the background. We just need to:
            //   1. dismiss the preflight overlay
            //   2. surface the running run in ResultsPanel (its tab)
            //   3. clear the chat input — we do NOT re-send via handleSend
            //      because that would dump the query into chat as a legacy
            //      message (which is what the user complained about).
            setPreflightQuery(null)
            setInput('')
            useSessionStore.getState().setActiveJobId(runId)
            useSessionStore.getState().setCol1Content({ type: 'pipeline_run', runId })
          }}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div
        className="px-3 text-[11px] font-semibold flex items-center justify-between"
        style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)', height: 36 }}
      >
                {/* Left: title + PIR badge */}
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ letterSpacing: '0.04em' }}>Agent</span>
          {pirGoal && (
            <span
              onClick={() => { setPirGoal(''); setShowPir(false) }}
              title={pirGoal}
              style={{
                fontSize: 8, fontWeight: 600, letterSpacing: '0.04em',
                color: 'var(--accent)', border: '1px solid var(--accent)',
                borderRadius: 8, padding: '1px 5px', cursor: 'pointer',
                maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
            >
              ◎ {pirGoal}
            </span>
          )}
        </span>

        {/* Right: clear/end + IS switch */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {messages.length > 0 && (
            <button
              onClick={sessionId ? handleEndSession : () => { clearMessages(); setPirGoal(''); setShowPir(false) }}
              title={sessionId ? 'End session and clear chat' : 'Clear chat'}
              style={{
                padding: '1px 6px', borderRadius: 10, fontSize: 8, fontWeight: 400,
                border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--muted)', cursor: 'pointer', letterSpacing: '0.02em',
              }}
            >{sessionId ? 'end' : 'clear'}</button>
          )}

          {/* IS toggle — proper switch */}
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', userSelect: 'none' }}
            onClick={() => setUseIntelligentSearch(prev => !prev)}
            title={
              !brainStatus?.ready
                ? 'IS unavailable — Claude Code not authenticated'
                : useIntelligentSearch ? 'Intelligent Search ON — click to disable' : 'Enable Intelligent Search'
            }
          >
            <span style={{ fontSize: 9, fontWeight: 600, color: useIntelligentSearch ? '#a78bfa' : 'var(--muted)', letterSpacing: '0.04em' }}>IS</span>
            {/* Track */}
            <div style={{
              position: 'relative', width: 28, height: 15, borderRadius: 8,
              background: useIntelligentSearch ? '#7c3aed' : '#334155',
              border: `1px solid ${useIntelligentSearch ? '#a78bfa' : '#475569'}`,
              transition: 'background 0.2s, border-color 0.2s',
              flexShrink: 0,
            }}>
              {/* Thumb */}
              <div style={{
                position: 'absolute', top: 2, borderRadius: '50%',
                width: 9, height: 9,
                background: useIntelligentSearch ? '#e9d5ff' : '#64748b',
                left: useIntelligentSearch ? 15 : 2,
                transition: 'left 0.2s, background 0.2s',
                boxShadow: useIntelligentSearch ? '0 0 4px #a78bfa88' : 'none',
              }} />
            </div>
            {/* Brain status dot */}
            <span style={{
              width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
              background: brainStatus?.ready ? '#4ade80' : '#f87171',
            }} title={brainStatus?.ready
              ? `Brain ready (${brainStatus.auth_method}${brainStatus.email ? ` — ${brainStatus.email}` : ''})`
              : brainStatus?.error ?? 'Not authenticated'
            } />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>
            Ask anything — I'll research it for you.
          </p>
        )}
        {messages.map(m => {
          // Question message — conversational feedback loop bubble
          if (m.type === 'question') {
            const runId = (m.payload?.run_id ?? '') as string
            const options = (m.payload?.options ?? []) as string[]
            const answered = answeredQuestions[m.id]
            const customVal = customAnswers[m.id] ?? ''

            return (
              <div key={m.id} style={{ margin: '6px 0 10px' }}>
                {/* Agent question bubble — left-aligned like agent messages */}
                <div style={{
                  display: 'inline-block', maxWidth: '85%',
                  background: 'var(--panel2)', border: '1px solid var(--border)',
                  borderRadius: '4px 12px 12px 12px',
                  padding: '8px 12px', fontSize: 11, color: 'var(--text)', lineHeight: 1.5,
                }}>
                  <span style={{ fontSize: 8, color: 'var(--accent)', fontWeight: 700, display: 'block', marginBottom: 3, letterSpacing: '0.06em' }}>
                    CLARIFYING
                  </span>
                  {m.content}
                </div>

                {/* Quick-reply options or answered state */}
                {answered ? (
                  <div style={{ marginTop: 4, marginLeft: 2 }}>
                    <span style={{
                      fontSize: 9, color: 'var(--muted)', fontStyle: 'italic',
                    }}>
                      ✓ {answered}
                    </span>
                  </div>
                ) : (
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {/* Option chips */}
                    {options.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                        {options.map((opt: string, i: number) => (
                          <button
                            key={i}
                            onClick={() => handleBrainAnswer(runId, opt, m.id)}
                            style={{
                              padding: '5px 12px', borderRadius: 16, fontSize: 10, fontWeight: 500,
                              border: '1px solid var(--accent)', background: 'transparent',
                              color: 'var(--accent)', cursor: 'pointer', transition: 'all 0.15s',
                            }}
                            onMouseEnter={e => {
                              (e.target as HTMLElement).style.background = 'var(--accent)'
                              ;(e.target as HTMLElement).style.color = '#000'
                            }}
                            onMouseLeave={e => {
                              (e.target as HTMLElement).style.background = 'transparent'
                              ;(e.target as HTMLElement).style.color = 'var(--accent)'
                            }}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Custom text answer */}
                    <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                      <input
                        type="text"
                        placeholder="Or type your answer…"
                        value={customVal}
                        onChange={e => setCustomAnswers(prev => ({ ...prev, [m.id]: e.target.value }))}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && customVal.trim()) {
                            handleBrainAnswer(runId, customVal.trim(), m.id)
                            setCustomAnswers(prev => ({ ...prev, [m.id]: '' }))
                          }
                        }}
                        style={{
                          flex: 1, fontSize: 10, padding: '4px 8px', borderRadius: 8,
                          border: '1px solid var(--border)', background: 'var(--panel2)',
                          color: 'var(--text)', outline: 'none',
                        }}
                      />
                      <button
                        onClick={() => {
                          if (customVal.trim()) {
                            handleBrainAnswer(runId, customVal.trim(), m.id)
                            setCustomAnswers(prev => ({ ...prev, [m.id]: '' }))
                          }
                        }}
                        disabled={!customVal.trim()}
                        style={{
                          padding: '4px 10px', borderRadius: 8, fontSize: 10,
                          border: '1px solid var(--border)', background: customVal.trim() ? 'var(--accent)' : 'transparent',
                          color: customVal.trim() ? '#000' : 'var(--muted)',
                          cursor: customVal.trim() ? 'pointer' : 'default',
                        }}
                      >
                        Send
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          }

          // Confirmation card — pipeline-layer gate for identification queries
          if (m.type === 'confirm') {
            const runId      = (m.payload?.run_id ?? '') as string
            const candidate      = (m.payload?.candidate ?? m.content) as string
            const desc           = (m.payload?.candidate_desc ?? '') as string
            const confidence     = (m.payload?.confidence ?? 0) as number
            const alts           = (m.payload?.alternatives ?? []) as string[]
            const candidateUrl   = (m.payload?.candidate_url ?? '') as string
            const candidateImage = (m.payload?.candidate_image ?? '') as string
            const answered       = answeredQuestions[m.id]

            return (
              <div key={m.id} style={{ margin: '6px 0 12px' }}>
                <div style={{
                  background: 'var(--panel2)', border: '1px solid var(--accent)',
                  borderRadius: '4px 12px 12px 12px', padding: '10px 14px',
                  maxWidth: '90%', fontSize: 11, color: 'var(--text)', lineHeight: 1.5,
                }}>
                  <span style={{ fontSize: 8, color: '#f59e0b', fontWeight: 700, display: 'block', marginBottom: 4, letterSpacing: '0.06em' }}>
                    RESULT FOUND — PLEASE CONFIRM
                  </span>
                  <div style={{ fontWeight: 600, marginBottom: 3 }}>{candidate}</div>
                  {candidateImage && (
                    <img
                      src={candidateImage}
                      alt={candidate}
                      style={{
                        width: '100%', maxHeight: 160, objectFit: 'cover',
                        borderRadius: 6, marginBottom: 6, display: 'block',
                      }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  )}
                  {desc && <div style={{ color: 'var(--text)', fontSize: 10, lineHeight: 1.6, marginBottom: 4 }}>{desc}</div>}
                  <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 6 }}>
                    Confidence: {confidence}%
                  </div>
                  {alts.length > 0 && (
                    <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 4 }}>
                      <span style={{ color: '#64748b', fontWeight: 600 }}>Also considered:</span>
                      {alts.map((alt, i) => (
                        <div key={i} style={{ marginLeft: 8, marginTop: 2, color: '#94a3b8' }}>· {alt}</div>
                      ))}
                    </div>
                  )}
                  {candidateUrl && (
                    <a
                      href={candidateUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block', marginTop: 8, fontSize: 9,
                        color: 'var(--accent)', textDecoration: 'none',
                        border: '1px solid var(--accent)', borderRadius: 8,
                        padding: '2px 8px', opacity: 0.85,
                      }}
                    >
                      View source ↗
                    </a>
                  )}
                </div>

                {answered ? (
                  <div style={{ marginTop: 4, marginLeft: 2 }}>
                    <span style={{ fontSize: 9, color: 'var(--muted)', fontStyle: 'italic' }}>✓ {answered}</span>
                  </div>
                ) : (
                  <div style={{ marginTop: 6, display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    {(['Yes, that\'s it', 'No, try another', 'Not sure'] as const).map((opt, i) => (
                      <button
                        key={i}
                        onClick={() => handleBrainAnswer(runId, opt, m.id)}
                        style={{
                          padding: '5px 12px', borderRadius: 16, fontSize: 10, fontWeight: 500,
                          border: `1px solid ${opt.startsWith('Yes') ? '#4ade80' : opt.startsWith('No') ? '#f87171' : 'var(--border)'}`,
                          background: 'transparent',
                          color: opt.startsWith('Yes') ? '#4ade80' : opt.startsWith('No') ? '#f87171' : 'var(--muted)',
                          cursor: 'pointer',
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

          // Change 3: enrichment plan messages render as BrainSuggestionBanner
          if (m.type === 'plan' && m.payload?.kind === 'enrichment') {
            return (
              <BrainSuggestionBanner
                key={m.id}
                suggestion={{
                  id: m.id,
                  kind: 'enrichment',
                  action: 'rerun-enriched',
                  title: m.content.split('\n')[0].replace(/\*\*/g, ''),
                  body: typeof m.payload?.body === 'string' ? m.payload.body : undefined,
                  payload: m.payload as Record<string, unknown>,
                  createdAt: Date.now(),
                }}
                onDismiss={() =>
                  useChatStore.getState().updateMessage(m.id, { type: 'message' })
                }
                onAction={async () => {
                  useChatStore.getState().updateMessage(m.id, { type: 'message' })
                }}
              />
            )
          }

          // Plan message — collapsible card
          if (m.type === 'plan') {
            const plan = (m.payload?.plan ?? {}) as { steps?: Record<string, unknown>[] }
            const steps = plan.steps ?? []
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
          const verificationStatus = m.payload?.verification_status as string | undefined
          return (
            <div key={m.id}>
              <MessageBubble role={m.role as 'user' | 'agent'} content={m.content} status={m.status} />
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

        {/* PIR inline field */}
        {showPir && (
          <div style={{
            marginBottom: 6, padding: '6px 8px',
            border: '1px solid var(--accent)', borderRadius: 6,
            background: 'var(--panel2)',
          }}>
            <div style={{ fontSize: 8, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.06em', marginBottom: 4 }}>
              ◎  WHAT MUST THIS INVESTIGATION ANSWER?
            </div>
            <input
              type="text"
              autoFocus
              placeholder="e.g. Find the current CEO and board of Company X"
              value={pirGoal}
              onChange={e => setPirGoal(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); setShowPir(false) }
                if (e.key === 'Escape') { e.preventDefault(); setPirGoal(''); setShowPir(false) }
              }}
              style={{
                width: '100%', fontSize: 10, padding: '3px 6px',
                borderRadius: 4, border: '1px solid var(--border)',
                background: 'transparent', color: 'var(--text)', outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        )}

        {/* Change 1: injection hint ring when a pipeline run is active */}
        <div className={cn('relative rounded-lg transition-all', hasActiveRun && 'ring-1 ring-violet-700/60')}>
          <textarea
            placeholder="Ask info-broker… (Enter to send)"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={sending}
            rows={4}
            className="w-full text-xs px-2 py-2 rounded resize-none outline-none disabled:opacity-50"
            style={{
              background: 'var(--panel2)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
            }}
          />
          {hasActiveRun && (
            <p className="text-[10px] text-violet-500/80 mt-1 flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              Pipeline running — your message will inject a node
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
