import React, { useState } from 'react'
import { useShare, ShareLink } from '@/hooks/useShare'

interface ShareDialogProps {
  runId: string
  open: boolean
  onClose: () => void
}

export function ShareDialog({ runId, open, onClose }: ShareDialogProps) {
  const { createShareLink, revokeShareLink, loading, error } = useShare(runId)
  const [ttlDays, setTtlDays] = useState(7)
  const [link, setLink] = useState<ShareLink | null>(null)
  const [copied, setCopied] = useState(false)
  const [revokeError, setRevokeError] = useState<string | null>(null)

  if (!open) return null

  async function handleCreate() {
    const result = await createShareLink(ttlDays)
    if (result) setLink(result)
  }

  async function handleCopy() {
    if (!link) return
    await navigator.clipboard.writeText(link.share_url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleRevoke() {
    if (!link) return
    setRevokeError(null)
    const ok = await revokeShareLink(link.token)
    if (ok) {
      setLink(null)
    } else {
      setRevokeError('Failed to revoke link.')
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Share run"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Share this run</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted-foreground hover:text-foreground transition-colors text-lg leading-none"
          >
            ×
          </button>
        </div>

        {!link && (
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-muted-foreground mb-1" htmlFor="ttl-days">
                Link expires after (days)
              </label>
              <input
                id="ttl-days"
                type="number"
                min={1}
                max={30}
                value={ttlDays}
                onChange={(e) => setTtlDays(Number(e.target.value))}
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              onClick={handleCreate}
              disabled={loading}
              className="w-full rounded-md bg-violet-600 hover:bg-violet-700 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
            >
              {loading ? 'Generating…' : 'Create share link'}
            </button>
          </div>
        )}

        {link && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Anyone with this link can view the run results (read-only).
              Expires: <span className="text-foreground">{new Date(link.expires_at).toLocaleDateString()}</span>
            </p>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={link.share_url}
                className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none select-all"
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <button
                onClick={handleCopy}
                className="rounded-md bg-border hover:bg-border/80 px-3 py-1.5 text-xs font-medium text-foreground transition-colors whitespace-nowrap"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            {revokeError && <p className="text-xs text-red-400">{revokeError}</p>}
            <button
              onClick={handleRevoke}
              disabled={loading}
              className="text-xs text-red-400 hover:text-red-300 underline disabled:opacity-50 transition-colors"
            >
              {loading ? 'Revoking…' : 'Revoke link'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
