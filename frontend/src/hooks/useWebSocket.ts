/// <reference types="vite/client" />
import { useEffect, useRef, useCallback } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { useChatStore } from '../stores/chatStore'
import { useRunStreamStore, type NodeCardStatus, type BrainSuggestion } from '../stores/runStreamStore'

export type WsEvent = {
  type: string
  job_id?: string
  run_id?: string       // pipeline run ID
  node_id?: string      // pipeline node ID
  plugin?: string
  status?: string
  result_count?: number
  message?: string
  // intelligent_search events
  call_id?: string
  parent_call_id?: string | null
  tool?: string
  params?: Record<string, unknown>
  input?: Record<string, unknown>  // is.tool_call full input
  call_count?: number
  max_calls?: number
  depth?: number
  query?: string
  result_preview?: string
  preview?: string
  query_preview?: string
  spec?: Record<string, unknown>
  // is.cycle event fields
  pir?: string
  hypotheses?: string[]
  cycle_id?: string
  parent_cycle_id?: string
  // pipeline.step.stream
  chunk?: string
  seq?: number
  // brain events
  intent?: string
  rationale?: string
  suggestion?: {
    id: string
    kind: 'enrichment' | 'next-step' | 'strategy'
    action?: string
    title: string
    body?: string
    payload?: Record<string, unknown>
    createdAt: number
  }
  suggestions?: Array<{
    id: string
    kind: 'enrichment' | 'next-step' | 'strategy'
    action?: string
    title: string
    body?: string
    payload?: Record<string, unknown>
    createdAt: number
  }>
  // pipeline.node.injected
  node_name?: string
  injected_by?: 'chat' | 'suggestion'
  after_node_id?: string
  // pipeline.node.injection_failed
  reason?: string
}

type Handler = (event: WsEvent) => void

// Singleton WebSocket shared across all hook consumers
let _ws: WebSocket | null = null
const _handlers = new Set<Handler>()
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null

function connect(token: string) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return

  const wsUrl = (import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/v3/stream') + `?token=${token}`
  _ws = new WebSocket(wsUrl)

  _ws.onmessage = (e) => {
    try {
      const event: WsEvent = JSON.parse(e.data)
      if (event.type !== 'ping') {
        // Handle fast+thorough phase events centrally
        switch (event.type) {
          case 'research.fast.started':
            useChatStore.getState().setThoroughInProgress(true)
            break
          case 'research.fast.completed':
            useChatStore.getState().setFastResearchDone(true)
            // Fast findings arrive via existing job.update/findings mechanism
            // This event signals "preview ready, thorough still running"
            break
          case 'research.thorough.started':
            // Both runs are underway — no extra state change needed
            break
          case 'research.thorough.completed':
            useChatStore.getState().setFastResearchDone(false)
            useChatStore.getState().setThoroughInProgress(false)
            break
        }
        // Central dispatch — pipeline/brain/injection events go directly to stores
        {
          const stream = useRunStreamStore.getState()
          const chat = useChatStore.getState()

          switch (event.type) {
            case 'pipeline.step.update': {
              if (!event.run_id || !event.node_id) break
              const isTerminal = ['succeeded', 'failed', 'canceled'].includes(event.status ?? '')
              stream.upsertCard(event.run_id, {
                nodeId: event.node_id,
                nodeName: event.plugin ?? event.node_id,
                status: (event.status as NodeCardStatus) ?? 'running',
                ...(event.status === 'running' ? { startedAt: Date.now() } : {}),
                ...(isTerminal ? { finishedAt: Date.now() } : {}),
                ...(event.result_preview || event.preview ? { preview: event.result_preview ?? event.preview ?? '' } : {}),
                ...(event.spec ? { output: event.spec } : {}),
              })
              break
            }

            case 'pipeline.step.stream': {
              if (!event.run_id || !event.node_id || !event.chunk) break
              stream.appendStreamChunk(event.run_id, event.node_id, event.chunk, event.seq ?? 0)
              break
            }

            case 'pipeline.run.complete': {
              if (!event.run_id) break
              const runStatus = event.status === 'canceled' ? 'canceled'
                : event.status === 'failed' ? 'failed'
                : 'succeeded'
              stream.setRunStatus(event.run_id, 'pipeline', runStatus as 'canceled' | 'failed' | 'succeeded')
              break
            }

            case 'pipeline.node.injected': {
              if (!event.run_id || !event.node_id) break
              stream.upsertCard(event.run_id, {
                nodeId: event.node_id,
                nodeName: event.node_name ?? event.node_id,
                status: 'pending',
                injectedBy: event.injected_by,
              })
              if (event.after_node_id) {
                stream.addEdge(event.run_id, {
                  from: event.after_node_id,
                  to: event.node_id,
                  kind: 'injected',
                })
              }
              break
            }

            case 'pipeline.node.injection_failed': {
              if (!event.run_id || !event.node_id) break
              stream.upsertCard(event.run_id, {
                nodeId: event.node_id,
                status: 'failed',
                preview: event.reason ?? 'Injection failed',
              })
              break
            }

            case 'intelligent_search.tool_call':
            case 'is.tool_call': {
              const rid = event.run_id ?? event.job_id ?? ''
              if (!rid) break
              // Mark this run as IS — also upgrades runs that were created with
              // default kind='pipeline' by an earlier non-IS-specific event.
              stream.setRunStatus(rid, 'is', 'running')
              stream.upsertCard(rid, {
                nodeId: event.call_id ?? event.node_id ?? rid,
                nodeName: event.tool ?? 'tool_call',
                status: 'running',
                startedAt: Date.now(),
                // Backend already sends a human-readable query_preview for each call —
                // store it as the card body so running cards aren't blank and the
                // modal's Formatted tab shows what the tool is searching for.
                // result_preview replaces this when the call succeeds.
                ...(event.query_preview ? { preview: event.query_preview } : {}),
                // Full input params for the modal's Input tab.
                ...(event.input && typeof event.input === 'object'
                  ? { input: event.input as Record<string, unknown> }
                  : {}),
                ...(event.pir ? { pir: event.pir } : {}),
              })
              break
            }

            case 'intelligent_search.tool_result':
            case 'is.tool_result': {
              const rid = event.run_id ?? event.job_id ?? ''
              if (!rid) break
              // Mark this run as IS — also upgrades runs that were created with
              // default kind='pipeline' by an earlier non-IS-specific event.
              stream.setRunStatus(rid, 'is', 'running')
              // Backend uses 'preview' for is.tool_result (agent.py:407); the
              // alternative result_preview is the pipeline-step.update field.
              // Try both so neither shape silently drops the content.
              const resultText = event.preview ?? event.result_preview ?? ''
              stream.upsertCard(rid, {
                nodeId: event.call_id ?? event.node_id ?? rid,
                status: 'succeeded',
                finishedAt: Date.now(),
                preview: resultText,
              })
              break
            }

            case 'brain.suggestion': {
              if (!event.run_id || !event.suggestion) break
              stream.addSuggestion(event.run_id, event.suggestion as BrainSuggestion)
              chat.appendBrainSuggestionAsMessage(event.suggestion as BrainSuggestion)
              break
            }

            case 'brain.enrichment': {
              if (!event.suggestions) break
              for (const sug of event.suggestions) {
                chat.addMessage({
                  id: sug.id,
                  role: 'assistant',
                  content: sug.body ? `**${sug.title}**\n\n${sug.body}` : sug.title,
                  status: 'done',
                  type: 'plan',
                  payload: { kind: 'enrichment', ...sug.payload },
                })
              }
              break
            }
          }
        }

        _handlers.forEach(h => h(event))
      }
    } catch {
      // ignore malformed messages
    }
  }

  _ws.onclose = () => {
    _ws = null
    if (_reconnectTimer) clearTimeout(_reconnectTimer)
    _reconnectTimer = setTimeout(() => {
      const t = localStorage.getItem('access_token')
      if (t) connect(t)
    }, 3000)
  }

  _ws.onerror = () => {
    _ws?.close()
  }
}

export function useWebSocket(onEvent: Handler) {
  const token = useSessionStore(s => s.accessToken)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  const stableHandler = useCallback((e: WsEvent) => handlerRef.current(e), [])

  useEffect(() => {
    if (!token) return
    connect(token)
    _handlers.add(stableHandler)
    return () => { _handlers.delete(stableHandler) }
  }, [token, stableHandler])
}
