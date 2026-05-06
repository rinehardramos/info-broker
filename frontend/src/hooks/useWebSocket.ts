import { useEffect, useRef, useCallback } from 'react'
import { useSessionStore } from '../stores/sessionStore'

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
  call_count?: number
  max_calls?: number
  depth?: number
  query?: string
  result_preview?: string
  spec?: Record<string, unknown>
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
