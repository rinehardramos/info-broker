import {
  useState,
  useRef,
  useEffect,
  useImperativeHandle,
  forwardRef,
  DragEvent,
  ChangeEvent,
} from 'react'
import { Upload, FileText, Loader2 } from 'lucide-react'
import { api } from '../../api/client'

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
    const inputRef = useRef<HTMLInputElement>(null)
    const onSourcesChangeRef = useRef(onSourcesChange)
    onSourcesChangeRef.current = onSourcesChange

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

    // Fetch existing sources on mount
    useEffect(() => {
      api
        .get('/v3/sources')
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
    }, [])

    async function uploadFile(file: File) {
      const tempId = `upload-${Date.now()}-${Math.random()}`

      applyUpdate(prev => [
        ...prev,
        { id: tempId, filename: file.name, status: 'uploading' },
      ])

      try {
        const formData = new FormData()
        formData.append('file', file)
        const res = await api.post('/v3/sources/upload', formData)
        const serverSource = res.data

        applyUpdate(prev =>
          prev.map(s =>
            s.id === tempId
              ? {
                  id: serverSource.id ?? tempId,
                  filename: serverSource.filename ?? file.name,
                  status: 'processing' as SourceStatus,
                }
              : s,
          ),
        )
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

    return (
      <div style={{ paddingBottom: 6 }}>
        {/* Thin drop-zone bar */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          style={{
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
      </div>
    )
  },
)

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
