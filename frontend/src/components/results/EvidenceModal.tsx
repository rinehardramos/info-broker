import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SourceClassBadge } from './SourceClassBadge'
import { EntityProfileCard } from './EntityProfileCard'
import { MediaEmbed, isEmbeddable } from './MediaEmbed'
import { api } from '@/api/client'
import type { RankedCandidate, RankedCandidateEvidence } from '@/types/research'

interface Props {
  open: boolean
  onClose: () => void
  candidate: RankedCandidate
  /** Run query — used to disambiguate the entity for profile enrichment. */
  context?: string
}

const IMAGE_EXT = /\.(jpe?g|png|gif|webp|avif|svg)(\?|$)/i
const VIDEO_EXT = /\.(mp4|webm|mov|m4v)(\?|$)/i
const AUDIO_EXT = /\.(mp3|wav|ogg|m4a|flac)(\?|$)/i

function kindOf(url?: string): 'image' | 'video' | 'audio' | 'page' {
  if (!url) return 'page'
  if (IMAGE_EXT.test(url)) return 'image'
  if (VIDEO_EXT.test(url)) return 'video'
  if (AUDIO_EXT.test(url)) return 'audio'
  return 'page'
}

interface LinkPreview {
  url: string
  title: string | null
  description: string | null
  image: string | null
  site_name: string | null
}

// Module-level cache so the same evidence URLs don't refetch across opens.
const _previewCache = new Map<string, LinkPreview | 'pending' | 'failed'>()

function useLinkPreview(url: string | undefined, enabled: boolean): LinkPreview | null {
  const [state, setState] = useState<LinkPreview | null>(() => {
    if (!url) return null
    const v = _previewCache.get(url)
    return (v && v !== 'pending' && v !== 'failed') ? v : null
  })

  useEffect(() => {
    if (!url || !enabled) return
    const cached = _previewCache.get(url)
    if (cached && cached !== 'pending' && cached !== 'failed') { setState(cached); return }
    if (cached === 'pending') return
    _previewCache.set(url, 'pending')
    let cancelled = false
    api.get<LinkPreview>('/v3/evidence/preview', { params: { url } })
      .then((r) => {
        if (cancelled) return
        _previewCache.set(url, r.data)
        setState(r.data)
      })
      .catch(() => {
        _previewCache.set(url, 'failed')
      })
    return () => { cancelled = true }
  }, [url, enabled])

  return state
}

function DirectMedia({ url }: { url: string }) {
  const kind = kindOf(url)
  if (kind === 'image') {
    return (
      <img src={url} alt="" loading="lazy"
        className="w-full max-h-64 object-contain rounded border border-border"
        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
      />
    )
  }
  if (kind === 'video') {
    return <video src={url} controls preload="metadata" className="w-full max-h-64 rounded border border-border" />
  }
  if (kind === 'audio') {
    return <audio src={url} controls preload="metadata" className="w-full" />
  }
  return null
}

function LinkPreviewCard({ url }: { url: string }) {
  const preview = useLinkPreview(url, true)
  if (!preview) {
    return (
      <div className="rounded border border-border bg-card/40 px-3 py-2 text-[10px] text-muted-foreground italic">
        Loading preview…
      </div>
    )
  }
  if (!preview.title && !preview.image && !preview.description) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className="block rounded border border-border bg-card/40 hover:bg-card/60 transition-colors overflow-hidden no-underline">
      {preview.image && (
        <img src={preview.image} alt={preview.title ?? ''} loading="lazy"
          className="w-full max-h-48 object-cover"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      )}
      <div className="px-3 py-2">
        {preview.site_name && (
          <p className="text-[9px] uppercase tracking-wide text-muted-foreground mb-0.5">{preview.site_name}</p>
        )}
        {preview.title && (
          <p className="text-xs font-medium text-foreground leading-snug line-clamp-2">{preview.title}</p>
        )}
        {preview.description && (
          <p className="text-[11px] text-foreground/75 mt-1 leading-relaxed line-clamp-3">{preview.description}</p>
        )}
      </div>
    </a>
  )
}

function EvidenceItem({ ev, index }: { ev: RankedCandidateEvidence; index: number }) {
  const url = ev.source_url
  const kind = kindOf(url)
  const embeddable = isEmbeddable(url)
  return (
    <div className={
      'rounded-md border px-3 py-2.5 ' +
      (ev.is_disconfirm ? 'border-red-900/40 bg-red-950/20' : 'border-border bg-card/40')
    }>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10px] font-bold text-muted-foreground">#{index + 1}</span>
        <SourceClassBadge sourceClass={ev.source_class} compact />
        {ev.is_disconfirm && (
          <span className="text-[9px] uppercase tracking-wide text-red-400 font-semibold">disconfirm</span>
        )}
      </div>
      <p className="text-xs leading-relaxed text-foreground/85 whitespace-pre-wrap">
        {ev.snippet || <span className="italic text-muted-foreground">No snippet recorded.</span>}
      </p>
      {url && (
        <div className="mt-2 space-y-2">
          {kind !== 'page' ? (
            <DirectMedia url={url} />
          ) : embeddable ? (
            <MediaEmbed url={url} />
          ) : (
            <LinkPreviewCard url={url} />
          )}
          <a href={url} target="_blank" rel="noopener noreferrer"
            className="inline-block text-[10px] text-sky-400 hover:underline break-all">
            {url}
          </a>
        </div>
      )}
    </div>
  )
}

export function EvidenceModal({ open, onClose, candidate, context }: Props) {
  const items = candidate.evidence ?? []
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-sm">
            Evidence for <span className="text-violet-300">{candidate.name}</span>
            <span className="ml-2 text-[10px] text-muted-foreground font-normal">
              {items.length} {items.length === 1 ? 'item' : 'items'} · confidence {Math.round((candidate.confidence ?? 0) * 100)}%
            </span>
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto pr-2 space-y-3">
          {open && (
            <EntityProfileCard
              name={candidate.name}
              context={context ?? ''}
              evidenceUrls={(candidate.evidence ?? [])
                .map(e => e.source_url)
                .filter((u): u is string => !!u)}
            />
          )}
          {items.length === 0 ? (
            <p className="text-xs text-muted-foreground italic py-4 text-center">
              No additional evidence snippets recorded.
            </p>
          ) : (
            <div className="space-y-2">
              {items.map((ev, i) => <EvidenceItem key={i} ev={ev} index={i} />)}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
