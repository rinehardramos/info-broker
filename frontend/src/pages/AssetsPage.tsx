/**
 * AssetsPage — library view of all uploaded assets (#106).
 *
 * Consumes the existing GET /v3/sources library endpoint (no session_id
 * filter = full library) and POST /v3/sources/upload. Upload happens here
 * the same way it does in FileUploadZone; the backing table is identical
 * so files uploaded via chat appear here automatically.
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import IconRail from '@/components/layout/IconRail'
import { api } from '@/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebouncedLoading } from '@/hooks/useDebouncedLoading'
import { Upload, Trash2, Copy, Search as SearchIcon } from 'lucide-react'

interface SourceRow {
  id: string
  filename: string
  file_type: string | null
  file_size_bytes: number | null
  status: string
  created_at: string
  session_id: string | null
  findings_count?: number | null
}

const ACCEPTED = '.csv,.xlsx,.xls,.parquet,.pdf,.doc,.docx,.txt'

function humanSize(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = bytes
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`
}

function statusColor(status: string): string {
  switch (status) {
    case 'indexed': return '#34d399'
    case 'ready':   return '#34d399'
    case 'processing':
    case 'parsing':
    case 'pending': return '#fbbf24'
    case 'failed':
    case 'error':   return '#f87171'
    default:        return 'var(--muted)'
  }
}

async function listSources(): Promise<SourceRow[]> {
  const res = await api.get<SourceRow[] | { sources: SourceRow[] }>('/v3/sources')
  return Array.isArray(res.data) ? res.data : (res.data.sources ?? [])
}

async function deleteSource(id: string): Promise<void> {
  await api.delete(`/v3/sources/${id}`)
}

async function uploadFile(file: File): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  await api.post('/v3/sources/upload', form)
}

export default function AssetsPage() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState('')
  const [dragging, setDragging] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const { data: sources, isLoading, isError, refetch } = useQuery<SourceRow[]>({
    queryKey: ['assets'],
    queryFn: listSources,
    refetchInterval: (q) => {
      // Poll while any row is still processing
      const rows = (q.state.data as SourceRow[] | undefined) ?? []
      return rows.some(r => r.status === 'processing' || r.status === 'pending' || r.status === 'parsing')
        ? 3000
        : false
    },
  })

  const showSkeleton = useDebouncedLoading(isLoading)

  const del = useMutation({
    mutationFn: deleteSource,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['assets'] }),
  })

  const upload = useMutation({
    mutationFn: uploadFile,
    onSuccess: () => {
      setUploadError(null)
      qc.invalidateQueries({ queryKey: ['assets'] })
    },
    onError: (err: unknown) => {
      const ax = err as { response?: { data?: { detail?: string } } }
      setUploadError(ax?.response?.data?.detail ?? 'Upload failed')
    },
  })

  function handleFiles(files: FileList | null) {
    if (!files) return
    setUploadError(null)
    Array.from(files).forEach(f => upload.mutate(f))
  }

  // Stop default browser drag-over so dropping anywhere on the page
  // doesn't navigate away when the user misses the dropzone.
  useEffect(() => {
    const stop = (e: DragEvent) => e.preventDefault()
    window.addEventListener('dragover', stop)
    window.addEventListener('drop', stop)
    return () => {
      window.removeEventListener('dragover', stop)
      window.removeEventListener('drop', stop)
    }
  }, [])

  const filtered = (sources ?? []).filter(s =>
    !filter || s.filename.toLowerCase().includes(filter.toLowerCase()),
  )

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Assets</h1>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>
            {sources ? `${sources.length} ${sources.length === 1 ? 'asset' : 'assets'}` : ''}
          </span>
        </div>

        {/* Upload zone */}
        <div
          data-testid="assets-dropzone"
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `1px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 8,
            padding: '24px 16px',
            textAlign: 'center',
            background: dragging ? 'rgba(167,139,250,0.06)' : 'var(--panel)',
            cursor: 'pointer',
            transition: 'background 0.12s, border-color 0.12s',
          }}
        >
          <Upload size={20} style={{ color: 'var(--muted)', marginBottom: 6 }} />
          <div style={{ fontSize: 12, color: 'var(--text)' }}>
            {upload.isPending ? 'Uploading…' : 'Drop files here or click to browse'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>
            Accepted: CSV, XLSX, XLS, Parquet, PDF, DOC, DOCX, TXT
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            onChange={e => { handleFiles(e.target.files); e.target.value = '' }}
            style={{ display: 'none' }}
            data-testid="assets-file-input"
          />
        </div>

        {uploadError && (
          <div style={{ fontSize: 12, color: '#f87171' }}>{uploadError}</div>
        )}

        {/* Search */}
        <div style={{ position: 'relative', maxWidth: 320 }}>
          <SearchIcon
            size={14}
            style={{ position: 'absolute', left: 8, top: 8, color: 'var(--muted)' }}
          />
          <input
            type="text"
            placeholder="Filter by filename…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            style={{
              width: '100%',
              padding: '6px 8px 6px 28px',
              fontSize: 12,
              border: '1px solid var(--border)',
              borderRadius: 4,
              background: 'var(--panel)',
              color: 'var(--text)',
              outline: 'none',
            }}
          />
        </div>

        {/* List */}
        {showSkeleton && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}

        {isError && !isLoading && (
          <div style={{ fontSize: 12, color: '#f87171' }}>
            Failed to load assets.{' '}
            <button
              onClick={() => refetch()}
              style={{ background: 'transparent', border: 'none', color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline' }}
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && filtered.length === 0 && (
          <div style={{ fontSize: 12, color: 'var(--muted)', padding: '24px 0', textAlign: 'center' }}>
            {sources && sources.length > 0
              ? 'No assets match that filter.'
              : 'No assets yet — drop a file above to get started.'}
          </div>
        )}

        {!isLoading && filtered.length > 0 && (
          <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--panel)', borderBottom: '1px solid var(--border)' }}>
                  {['Filename', 'Type', 'Size', 'Status', 'Uploaded', ''].map(h => (
                    <th
                      key={h}
                      style={{
                        padding: '8px 12px',
                        textAlign: 'left',
                        color: 'var(--subtext)',
                        fontWeight: 500,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => (
                  <tr key={s.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 12px', color: 'var(--text)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.filename}>
                      {s.filename}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--subtext)', textTransform: 'uppercase', fontSize: 10 }}>
                      {s.file_type ?? '—'}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--subtext)', whiteSpace: 'nowrap' }}>
                      {humanSize(s.file_size_bytes)}
                    </td>
                    <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                      <span style={{ color: statusColor(s.status), fontSize: 11 }}>● {s.status}</span>
                      {typeof s.findings_count === 'number' && s.findings_count > 0 && (
                        <span style={{ color: 'var(--muted)', marginLeft: 6, fontSize: 10 }}>
                          {s.findings_count} findings
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: 11, whiteSpace: 'nowrap' }}>
                      {s.created_at ? new Date(s.created_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', textAlign: 'right' }}>
                      <button
                        onClick={() => navigator.clipboard?.writeText(s.id)}
                        title="Copy ID"
                        style={{
                          padding: 4, background: 'transparent', border: 'none',
                          color: 'var(--muted)', cursor: 'pointer', marginRight: 4,
                        }}
                      >
                        <Copy size={13} />
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm(`Delete ${s.filename}? This cannot be undone.`)) {
                            del.mutate(s.id)
                          }
                        }}
                        disabled={del.isPending}
                        title="Delete"
                        data-testid={`delete-${s.id}`}
                        style={{
                          padding: 4, background: 'transparent', border: 'none',
                          color: '#f87171', cursor: del.isPending ? 'not-allowed' : 'pointer',
                          opacity: del.isPending ? 0.5 : 1,
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <IconRail />
    </div>
  )
}
