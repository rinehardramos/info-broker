import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listMonitors, createMonitor, deleteMonitor, type MonitorOut } from '../api/v3'
import IconRail from '../components/layout/IconRail'
import { Skeleton } from '../components/ui/skeleton'

export default function Monitors() {
  const qc = useQueryClient()
  const { data: monitors = [], isLoading } = useQuery({ queryKey: ['monitors'], queryFn: listMonitors })

  const [name, setName]     = useState('')
  const [type, setType]     = useState('rss')
  const [target, setTarget] = useState('')
  const [interval, setInterval] = useState(60)

  const create = useMutation({
    mutationFn: () => createMonitor({ name, type, target, poll_interval_minutes: interval }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monitors'] })
      setName(''); setTarget('')
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteMonitor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['monitors'] }),
  })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 col-scroll p-4">
        <h2 className="text-sm font-bold mb-4" style={{ color: 'var(--accent)' }}>Feed Monitors</h2>

        <div className="mb-4 p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
          <div className="text-[11px] font-semibold mb-2" style={{ color: 'var(--subtext)' }}>Add Monitor</div>
          <div className="flex flex-col gap-2">
            <input placeholder="Name" value={name} onChange={e => setName(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <select value={type} onChange={e => setType(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}>
              <option value="rss">RSS</option>
              <option value="twitter">Twitter / X</option>
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook</option>
            </select>
            <input placeholder="URL or @handle" value={target} onChange={e => setTarget(e.target.value)}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <input type="number" placeholder="Poll interval (min)" value={interval}
              onChange={e => setInterval(Number(e.target.value))}
              className="px-2 py-1 rounded text-xs outline-none"
              style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }} />
            <button
              onClick={() => create.mutate()}
              disabled={!name || !target || create.isPending}
              className="px-3 py-1 rounded text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--accent)', color: 'var(--bg)', cursor: 'pointer', border: 'none' }}
            >
              {create.isPending ? 'Adding…' : 'Add Monitor'}
            </button>
          </div>
        </div>

        {isLoading && (
          <div className="space-y-1.5" aria-busy="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}
        {monitors.map((m: MonitorOut) => (
          <div key={m.id} className="mb-2 p-3 rounded flex items-center justify-between text-xs"
            style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text)' }}>{m.name}</span>
              <span className="ml-2" style={{ color: 'var(--subtext)' }}>{m.type} · {m.target}</span>
              {m.last_polled_at && (
                <span className="ml-2" style={{ color: 'var(--muted)' }}>
                  polled {new Date(m.last_polled_at).toLocaleString()}
                </span>
              )}
            </div>
            <button
              onClick={() => remove.mutate(m.id)}
              style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11 }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <IconRail />
    </div>
  )
}
