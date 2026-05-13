import { useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Download, Loader2, ChevronDown } from 'lucide-react'
import { createExport, getExport, type ExportFormat } from '@/api/v3'

interface Props {
  runId: string
  pollIntervalMs?: number
}

export function DownloadMenu({ runId, pollIntervalMs = 2000 }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function pollUntilReady(exportId: string): Promise<void> {
    while (true) {
      const exp = await getExport(exportId)
      if (exp.status === 'ready') {
        window.location.href = exp.download_url ?? `/v3/exports/${exportId}/download`
        return
      }
      if (exp.status === 'failed') throw new Error(exp.error ?? 'export failed')
      await new Promise<void>((r) => setTimeout(r, pollIntervalMs))
    }
  }

  async function start(format: ExportFormat) {
    setBusy(true)
    setError(null)
    try {
      const exp = await createExport(runId, format)
      if (exp.status === 'ready' && exp.download_url) {
        window.location.href = exp.download_url
      } else {
        await pollUntilReady(exp.id)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'export error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={busy} aria-label="Download">
          {busy
            ? <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            : <Download className="h-3 w-3 mr-1" />}
          Download
          <ChevronDown className="h-3 w-3 ml-1" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => start('csv')}>Export as CSV</DropdownMenuItem>
        <DropdownMenuItem onClick={() => start('xlsx')}>Export as XLSX</DropdownMenuItem>
        {error && <DropdownMenuItem disabled className="text-red-600">{error}</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
