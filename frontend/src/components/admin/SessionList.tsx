import { useState, useEffect, useCallback } from 'react'
import { listMcpSessions, getMcpSession, McpSession, McpToolCall } from '../../api/v3'
import { useWebSocket, WsEvent } from '../../hooks/useWebSocket'

const MCP_WS_EVENTS = new Set([
  'mcp.session.start',
  'mcp.session.complete',
  'mcp.tool_call.start',
  'mcp.tool_call.complete',
])

function statusDot(status: string) {
  let color = 'var(--muted)'
  if (status === 'active') color = '#4ade80'
  else if (status === 'failed') color = 'var(--danger)'
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
      }}
    />
  )
}

function callStatusDot(status: string) {
  let color = 'var(--muted)'
  if (status === 'success') color = '#4ade80'
  else if (status === 'error') color = 'var(--danger)'
  else if (status === 'running') color = 'var(--accent)'
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
      }}
    />
  )
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString()
}

export default function SessionList() {
  const [sessions, setSessions] = useState<McpSession[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [calls, setCalls] = useState<McpToolCall[]>([])
  const [loadingCalls, setLoadingCalls] = useState(false)

  const fetchSessions = useCallback(async () => {
    try {
      const data = await listMcpSessions()
      setSessions(data)
    } catch {
      // silently ignore poll errors
    }
  }, [])

  useEffect(() => {
    fetchSessions()
    const interval = setInterval(fetchSessions, 5000)
    return () => clearInterval(interval)
  }, [fetchSessions])

  useWebSocket(
    useCallback((event: WsEvent) => {
      if (MCP_WS_EVENTS.has(event.type)) {
        fetchSessions()
      }
    }, [fetchSessions])
  )

  const selectSession = useCallback(async (id: string) => {
    setSelectedId(id)
    setLoadingCalls(true)
    try {
      const detail = await getMcpSession(id)
      setCalls(detail.calls)
    } catch {
      setCalls([])
    } finally {
      setLoadingCalls(false)
    }
  }, [])

  // Re-fetch calls when WS fires for the selected session
  useWebSocket(
    useCallback((event: WsEvent) => {
      if (selectedId && MCP_WS_EVENTS.has(event.type)) {
        getMcpSession(selectedId)
          .then(d => setCalls(d.calls))
          .catch(() => {})
      }
    }, [selectedId])
  )

  return (
    <div className="flex flex-1 min-h-0" style={{ gap: 0 }}>
      {/* Left: session table */}
      <div
        className="flex flex-col min-h-0 overflow-auto"
        style={{
          width: '45%',
          borderRight: '1px solid var(--border)',
        }}
      >
        <div
          className="px-3 py-2 text-[11px] font-semibold sticky top-0"
          style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', color: 'var(--muted)' }}
        >
          Sessions ({sessions.length})
        </div>
        {sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs" style={{ color: 'var(--muted)' }}>No sessions found.</div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Status</th>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Caller</th>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Type</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Calls</th>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Started</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map(s => (
                <tr
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  style={{
                    cursor: 'pointer',
                    background: selectedId === s.id ? 'var(--surface)' : 'transparent',
                    borderBottom: '1px solid var(--border)',
                  }}
                  onMouseEnter={e => { if (selectedId !== s.id) (e.currentTarget as HTMLElement).style.background = 'var(--panel)' }}
                  onMouseLeave={e => { if (selectedId !== s.id) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1.5">
                      {statusDot(s.status)}
                      <span style={{ color: 'var(--muted)', fontSize: 10 }}>{s.status}</span>
                    </div>
                  </td>
                  <td className="px-3 py-1.5" style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text)' }}>
                    {s.caller_identity}
                  </td>
                  <td className="px-3 py-1.5" style={{ color: 'var(--muted)' }}>{s.session_type}</td>
                  <td className="px-3 py-1.5 text-right" style={{ color: 'var(--text)' }}>{s.tool_call_count}</td>
                  <td className="px-3 py-1.5" style={{ color: 'var(--muted)' }}>{formatTime(s.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Right: call detail */}
      <div className="flex flex-col flex-1 min-h-0 overflow-auto">
        <div
          className="px-3 py-2 text-[11px] font-semibold sticky top-0"
          style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', color: 'var(--muted)' }}
        >
          {selectedId ? `Tool Calls` : 'Select a session'}
        </div>
        {!selectedId && (
          <div className="px-3 py-4 text-xs" style={{ color: 'var(--muted)' }}>Click a session to view its tool calls.</div>
        )}
        {selectedId && loadingCalls && (
          <div className="px-3 py-4 text-xs" style={{ color: 'var(--muted)' }}>Loading…</div>
        )}
        {selectedId && !loadingCalls && calls.length === 0 && (
          <div className="px-3 py-4 text-xs" style={{ color: 'var(--muted)' }}>No tool calls recorded.</div>
        )}
        {selectedId && !loadingCalls && calls.length > 0 && (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Status</th>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Tool</th>
                <th className="px-3 py-1 text-right text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Duration</th>
                <th className="px-3 py-1 text-left text-[10px] font-medium" style={{ color: 'var(--muted)' }}>Result / Error</th>
              </tr>
            </thead>
            <tbody>
              {calls.map(c => (
                <tr key={c.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1.5">
                      {callStatusDot(c.status)}
                      <span style={{ color: 'var(--muted)', fontSize: 10 }}>{c.status}</span>
                    </div>
                  </td>
                  <td className="px-3 py-1.5" style={{ color: 'var(--text)' }}>{c.tool_name}</td>
                  <td className="px-3 py-1.5 text-right" style={{ color: 'var(--muted)' }}>
                    {c.duration_ms != null ? `${c.duration_ms}ms` : '—'}
                  </td>
                  <td
                    className="px-3 py-1.5"
                    style={{
                      maxWidth: 240,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      color: c.error_message ? 'var(--danger)' : 'var(--muted)',
                    }}
                  >
                    {c.error_message ?? c.result_preview ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
