import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'
import { StatusBadge } from './StatusBadge'
import { DownloadMenu } from './DownloadMenu'
import { api } from '@/api/client'

interface RunDetail {
  id: string
  status: string
  query: string
  pipeline_name: string
  trigger_type: string
  started_at: string
  finished_at: string | null
  error_message: string | null
  research?: {
    findings?: Array<{
      title?: string
      content?: string
      snippet?: string
      url?: string
      source?: string
      confidence?: number
    }>
    summary?: string
    query?: string
  } | null
}

async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const { data } = await api.get<RunDetail>(`/v3/pipelines/runs/${runId}`)
  return data
}

export function ResultDrawer() {
  const { isOpen, runId, close } = useResultDrawerStore()
  const [tab, setTab] = useState('findings')

  useEffect(() => { if (!isOpen) setTab('findings') }, [isOpen])

  const { data: run, isLoading } = useQuery({
    queryKey: ['run-detail', runId],
    queryFn: () => fetchRunDetail(runId!),
    enabled: Boolean(isOpen && runId),
  })

  const findings = run?.research?.findings ?? []

  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) close() }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[680px] lg:max-w-[52vw] flex flex-col overflow-hidden p-0"
        style={{
          background: 'var(--panel)',
          borderLeft: '1px solid var(--border)',
          color: 'var(--text)',
        }}
      >
        {/* Header */}
        <SheetHeader className="px-5 pt-5 pb-3 flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
          <SheetTitle className="truncate text-sm font-semibold" style={{ color: 'var(--text)' }}>
            {isLoading ? 'Loading…' : (run?.query ?? `Run ${runId?.slice(0, 8)}…`)}
          </SheetTitle>
          <SheetDescription className="flex items-center gap-2 mt-1">
            {run && <StatusBadge status={run.status} />}
            {run?.pipeline_name && (
              <Badge variant="outline" className="text-xs" style={{ borderColor: 'var(--border)', color: 'var(--subtext)' }}>
                {run.pipeline_name}
              </Badge>
            )}
            {run?.started_at && (
              <span className="text-xs" style={{ color: 'var(--muted)' }}>
                {new Date(run.started_at).toLocaleString()}
              </span>
            )}
          </SheetDescription>
        </SheetHeader>

        {/* Tabs */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <Tabs value={tab} onValueChange={setTab} className="flex flex-col h-full">
            <TabsList className="mx-5 mt-3 flex-shrink-0 self-start" style={{ background: 'var(--panel2)' }}>
              <TabsTrigger value="findings">
                Findings {findings.length > 0 && <span className="ml-1 opacity-60">({findings.length})</span>}
              </TabsTrigger>
              <TabsTrigger value="summary">Summary</TabsTrigger>
              <TabsTrigger value="raw">Raw JSON</TabsTrigger>
            </TabsList>

            <TabsContent value="findings" className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
              {isLoading && <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading findings…</p>}
              {!isLoading && findings.length === 0 && (
                <p className="text-xs" style={{ color: 'var(--muted)' }}>
                  {run?.status === 'failed'
                    ? `Run failed: ${run.error_message ?? 'unknown error'}`
                    : 'No findings available for this run.'}
                </p>
              )}
              {findings.map((f, i) => (
                <div
                  key={i}
                  className="rounded-md p-3 text-xs"
                  style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
                >
                  {f.title && <div className="font-semibold mb-1" style={{ color: 'var(--text)' }}>{f.title}</div>}
                  {(f.content ?? f.snippet) && (
                    <div className="mb-2 leading-relaxed" style={{ color: 'var(--subtext)' }}>
                      {(f.content ?? f.snippet)?.slice(0, 400)}
                      {((f.content ?? f.snippet)?.length ?? 0) > 400 && '…'}
                    </div>
                  )}
                  <div className="flex items-center gap-3 flex-wrap">
                    {f.source && (
                      <span style={{ color: 'var(--muted)' }}>{f.source}</span>
                    )}
                    {f.confidence !== undefined && (
                      <span style={{ color: 'var(--accent)' }}>{Math.round(f.confidence * 100)}% confidence</span>
                    )}
                    {f.url && (
                      <a
                        href={f.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline truncate max-w-xs"
                        style={{ color: 'var(--accent)' }}
                      >
                        {f.url}
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </TabsContent>

            <TabsContent value="summary" className="flex-1 overflow-y-auto px-5 py-3">
              {run?.research?.summary ? (
                <p className="text-sm leading-relaxed" style={{ color: 'var(--subtext)' }}>
                  {run.research.summary}
                </p>
              ) : (
                <p className="text-xs" style={{ color: 'var(--muted)' }}>No summary available.</p>
              )}
            </TabsContent>

            <TabsContent value="raw" className="flex-1 overflow-y-auto px-5 py-3">
              <pre className="text-xs whitespace-pre-wrap" style={{ color: 'var(--subtext)' }}>
                {JSON.stringify(run ?? { runId }, null, 2)}
              </pre>
            </TabsContent>
          </Tabs>
        </div>

        {/* Footer */}
        <SheetFooter
          className="px-5 py-3 flex-shrink-0"
          style={{ borderTop: '1px solid var(--border)', background: 'var(--panel)' }}
        >
          {runId ? <DownloadMenu runId={runId} /> : null}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
