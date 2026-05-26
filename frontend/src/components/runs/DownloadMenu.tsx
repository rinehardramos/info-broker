import { useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Download, Loader2, ChevronDown } from 'lucide-react'
import { createExport, type ExportFormat } from '@/api/v3'
import { api } from '@/api/client'

interface Props {
  runId: string
}

export function DownloadMenu({ runId }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start(format: ExportFormat) {
    setBusy(true)
    setError(null)
    try {
      // Export is synchronous: returns { filename, url }. Fetch the file through
      // the authenticated API client as a blob, then trigger a browser download
      // (robust across dev proxy / prod origin, vs window.location on a relative URL).
      const exp = await createExport(runId, format)
      const resp = await api.get(exp.url, { responseType: 'blob' })
      const blobUrl = URL.createObjectURL(resp.data as Blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = exp.filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'export error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="inline-flex flex-col items-end">
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
        {/* solid bg: bg-popover now resolves (popover color added to the theme) */}
        <DropdownMenuContent align="end" className="bg-popover">
          <DropdownMenuItem onClick={() => start('csv')}>Export as CSV</DropdownMenuItem>
          <DropdownMenuItem onClick={() => start('xlsx')}>Export as XLSX</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {/* error shown OUTSIDE the dropdown (which closes on select), so it stays visible */}
      {error && <span role="alert" className="text-xs text-red-500 mt-1 max-w-[200px] text-right">{error}</span>}
    </div>
  )
}
