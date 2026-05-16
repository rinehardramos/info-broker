import {
  useState,
  useRef,
  useEffect,
  useImperativeHandle,
  forwardRef,
  DragEvent,
  ChangeEvent,
} from 'react'
import { Upload, FileText, Loader2, Library } from 'lucide-react'
import { api } from '../../api/client'
import { useChatStore } from '../../stores/chatStore'

export type SourceStatus = 'uploading' | 'processing' | 'indexed' | 'failed'

export interface UploadedSource {
  id: string
  filename: string
  status: SourceStatus
  findingsCount?: number
}

export interface FileUploadZoneHandle {
  updateSource: (id: string, patch: Partial<UploadedSource>) => void
}

interface FileUploadZoneProps {
  onSourcesChange?: (sources: UploadedSource[]) => void
}

const ACCEPTED_TYPES = '.csv,.xlsx,.xls,.pdf,.doc,.docx,.txt'

function mapApiStatus(apiStatus: string): SourceStatus {
  if (apiStatus === 'indexed') return 'indexed'
  if (apiStatus === 'failed' || apiStatus === 'error') return 'failed'
  return 'processing'
}

const FileUploadZone = forwardRef<FileUploadZoneHandle, FileUploadZoneProps>(
  function FileUploadZone({ onSourcesChange }, ref) {
    const [sources, setSources] = useState<UploadedSource[]>([])
    const [dragging, setDragging] = useState(false)
    const [showLibrary, setShowLibrary] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)
    const onSourcesChangeRef = useRef(onSourcesChange)
    onSourcesChangeRef.current = onSourcesChange
    // Active chat session — uploads scope here so files don't bleed across
    // sessions. Null means no active session yet (file becomes a library item).
    const sessionId = useChatStore(s => s.sessionId)

    function applyUpdate(updater: (prev: UploadedSource[]) => UploadedSource[]) {
      setSources(prev => {
        const next = updater(prev)
        onSourcesChangeRef.current?.(next)
        return next
      })
    }

    useImperativeHandle(ref, () => ({
      updateSource(id: string, patch: Partial<UploadedSource>) {
        applyUpdate(prev =>
          prev.map(s => (s.id === id ? { ...s, ...patch } : s)),
        )
      },
    }))

    // Fetch sources scoped to the current session. When sessionId changes,
    // refetch so we don't leak prior-session uploads into a new chat.
    useEffect(() => {
      const params = sessionId ? `?session_id=${sessionId}` : ''
      api
        .get(`/v3/sources${params}`)
        .then(res => {
          const raw: Array<{
            id: string
            filename: string
            status: string
            findings_count?: number
          }> = res.data?.sources ?? res.data ?? []

          const mapped: UploadedSource[] = raw.map(s => ({
            id: s.id,
            filename: s.filename,
            status: mapApiStatus(s.status),
            findingsCount: s.findings_count,
          }))

          setSources(mapped)
          onSourcesChangeRef.current?.(mapped)
        })
        .catch(() => {
          // sources panel is non-critical — silently ignore fetch failures
        })
    }, [sessionId])

    async function uploadFile(file: File) {
      const tempId = `upload-${Date.now()}-${Math.random()}`

      applyUpdate(prev => [
        ...prev,
        { id: tempId, filename: file.name, status: 'uploading' },
      ])

      try {
        const formData = new FormData()
        formData.append('file', file)
        if (sessionId) formData.append('session_id', sessionId)
        const res = await api.post('/v3/sources/upload', formData)
        const serverSource = res.data
        const sourceId = serverSource.source_id ?? serverSource.id ?? tempId

        applyUpdate(prev =>
          prev.map(s =>
            s.id === tempId
              ? {
                  id: sourceId,
                  filename: serverSource.filename ?? file.name,
                  status: 'processing' as SourceStatus,
                }
              : s,
          ),
        )

        // Poll until indexed/failed (WS events may be missed)
        if (sourceId && !sourceId.startsWith('upload-')) {
          const poll = setInterval(async () => {
            try {
              const check = await api.get(`/v3/sources/${sourceId}`)
              const s = check.data
              if (s.status === 'indexed' || s.status === 'failed') {
                clearInterval(poll)
                applyUpdate(prev =>
                  prev.map(src =>
                    src.id === sourceId
                      ? { ...src, status: mapApiStatus(s.status), findingsCount: s.findings_count }
                      : src,
                  ),
                )
              }
            } catch { clearInterval(poll) }
          }, 2000)
          // Safety: stop polling after 5 min
          setTimeout(() => clearInterval(poll), 300_000)
        }
      } catch {
        applyUpdate(prev =>
          prev.map(s =>
            s.id === tempId ? { ...s, status: 'failed' as SourceStatus } : s,
          ),
        )
      }
    }

    function handleFiles(files: FileList | null) {
      if (!files) return
      Array.from(files).forEach(uploadFile)
    }

    function onInputChange(e: ChangeEvent<HTMLInputElement>) {
      handleFiles(e.target.files)
      e.target.value = ''
    }

    function onDragOver(e: DragEvent<HTMLDivElement>) {
      e.preventDefault()
      setDragging(true)
    }

    function onDragLeave() {
      setDragging(false)
    }

    function onDrop(e: DragEvent<HTMLDivElement>) {
      e.preventDefault()
      setDragging(false)
      handleFiles(e.dataTransfer.files)
    }

    function removeSource(id: string) {
      applyUpdate(prev => prev.filter(s => s.id !== id))
      if (!id.startsWith('upload-')) {
        api.delete(`/v3/sources/${id}`).catch(() => {})
      }
    }

    function attachFromLibrary(srcId: string) {
      if (!sessionId) return
      api.post(`/v3/sources/${srcId}/attach`, { session_id: sessionId })
        .then(() => {
          // refetch session-scoped list
          api.get(`/v3/sources?session_id=${sessionId}`).then(res => {
            const raw = res.data?.sources ?? res.data ?? []
            const mapped: UploadedSource[] = raw.map((s: { id: string; filename: string; status: string; findings_count?: number }) => ({
              id: s.id,
              filename: s.filename,
              status: mapApiStatus(s.status),
              findingsCount: s.findings_count,
            }))
            setSources(mapped)
            onSourcesChangeRef.current?.(mapped)
          })
          setShowLibrary(false)
        })
        .catch(() => { /* keep dialog open */ })
    }

    return (
      <div style={{ paddingBottom: 6 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {/* Thin drop-zone bar */}
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 10px',
              borderRadius: 6,
              border: `1px dashed ${dragging ? '#6366f1' : 'var(--border)'}`,
              background: dragging ? 'rgba(99,102,241,0.08)' : 'transparent',
              cursor: 'pointer',
              fontSize: 11,
              color: 'var(--muted)',
              transition: 'all 0.15s',
              userSelect: 'none',
            }}
          >
            <Upload size={12} />
            <span>Drop files or click to upload</span>
          </div>
          {/* From-library trigger — only meaningful when we have an
              active session to attach into. */}
          {sessionId && (
            <button
              type="button"
              onClick={() => setShowLibrary(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 10px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 11,
                color: 'var(--muted)',
                whiteSpace: 'nowrap',
              }}
              title="Attach a file you've uploaded previously"
            >
              <Library size={12} />
              <span>Library</span>
            </button>
          )}
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES}
          style={{ display: 'none' }}
          onChange={onInputChange}
        />

        {/* Source chips */}
        {sources.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', marginTop: 4 }}>
            {sources.map(source => (
              <SourceChip
                key={source.id}
                source={source}
                onRemove={() => removeSource(source.id)}
              />
            ))}
          </div>
        )}
        {showLibrary && (
          <LibraryPicker
            currentSessionId={sessionId}
            attachedIds={new Set(sources.map(s => s.id))}
            onAttach={attachFromLibrary}
            onClose={() => setShowLibrary(false)}
          />
        )}
      </div>
    )
  },
)

// ---- Library picker ----

interface LibraryItem {
  id: string
  filename: string
  status: string
  findings_count?: number
  created_at?: string
}

function LibraryPicker({
  currentSessionId,
  attachedIds,
  onAttach,
  onClose,
}: {
  currentSessionId: string | null
  attachedIds: Set<string>
  onAttach: (id: string) => void
  onClose: () => void
}) {
  const [items, setItems] = useState<LibraryItem[]>([])
  useEffect(() => {
    api.get('/v3/sources').then(res => {
      const raw: LibraryItem[] = res.data?.sources ?? res.data ?? []
      setItems(raw)
    }).catch(() => setItems([]))
  }, [])
  const available = items.filter(i => !attachedIds.has(i.id))
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 60,
        background: 'rgba(0,0,0,0.5)', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--panel)', color: 'var(--text)',
          width: 480, maxHeight: '70vh', overflow: 'auto',
          borderRadius: 10, padding: 16,
          border: '1px solid var(--border)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
          <strong style={{ fontSize: 13 }}>Attach from library</strong>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer' }}>✕</button>
        </div>
        {available.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            No other files in your library yet.
          </div>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {available.map(it => (
              <li key={it.id} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '6px 0', borderBottom: '1px solid var(--border)',
              }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.filename}</div>
                  <div style={{ fontSize: 10, color: 'var(--muted)' }}>
                    {it.status}{it.findings_count != null ? ` · ${it.findings_count} findings` : ''}
                  </div>
                </div>
                <button
                  onClick={() => onAttach(it.id)}
                  disabled={!currentSessionId}
                  style={{
                    fontSize: 11, padding: '3px 8px',
                    border: '1px solid var(--border)', borderRadius: 4,
                    background: 'transparent', color: 'var(--accent)',
                    cursor: currentSessionId ? 'pointer' : 'not-allowed',
                  }}
                >
                  Attach
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export default FileUploadZone

// ---- SourceChip ----

interface SourceChipProps {
  source: UploadedSource
  onRemove: () => void
}

function SourceChip({ source, onRemove }: SourceChipProps) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 10px',
        borderRadius: 12,
        background: 'rgba(99,102,241,0.15)',
        color: '#a5b4fc',
        fontSize: 12,
        marginRight: 6,
        marginBottom: 4,
      }}
    >
      <FileText size={12} />
      {source.filename}
      {(source.status === 'uploading' || source.status === 'processing') && (
        <Loader2 size={12} className="animate-spin" />
      )}
      {source.status === 'indexed' && (
        <span style={{ color: '#4ade80' }}>
          {source.findingsCount !== undefined ? `(${source.findingsCount})` : ''}
        </span>
      )}
      {source.status === 'failed' && (
        <span style={{ color: '#f87171' }}>failed</span>
      )}
      <button
        onClick={onRemove}
        style={{
          background: 'none',
          border: 'none',
          color: '#888',
          cursor: 'pointer',
          padding: 0,
          marginLeft: 4,
        }}
      >
        x
      </button>
    </div>
  )
}
