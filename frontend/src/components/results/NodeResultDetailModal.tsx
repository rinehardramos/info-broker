import React, { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogBody,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { NodeCard } from '@/stores/runStreamStore'

interface NodeResultDetailModalProps {
  card: NodeCard | null
  open: boolean
  onClose: () => void
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="text-[10px] px-2 py-0.5 rounded bg-muted hover:bg-muted/80 text-muted-foreground transition-colors"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

function RawTab({ card }: { card: NodeCard }) {
  const text = JSON.stringify(card.output ?? { preview: card.preview }, null, 2)
  return (
    <div className="relative">
      <div className="absolute right-2 top-2">
        <CopyButton text={text} />
      </div>
      <pre className="text-xs text-foreground/80 bg-muted/30 rounded p-3 overflow-auto max-h-96 whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  )
}

function FormattedTab({ card }: { card: NodeCard }) {
  const content =
    card.preview ||
    (typeof card.output === 'string'
      ? card.output
      : JSON.stringify(card.output, null, 2))
  return (
    <div className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
      {content || (
        <span className="text-muted-foreground italic">No formatted output yet.</span>
      )}
    </div>
  )
}

function SourcesTab({ card }: { card: NodeCard }) {
  if (!card.sources?.length) {
    return <p className="text-sm text-muted-foreground italic">No sources recorded.</p>
  }
  return (
    <ul className="space-y-2">
      {card.sources.map((s, i) => (
        <li key={i} className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground flex-1 truncate">
            {s.label ?? s.url ?? 'Unknown source'}
          </span>
          {s.url && <CopyButton text={s.url} />}
        </li>
      ))}
    </ul>
  )
}

function BranchTab({ card }: { card: NodeCard }) {
  return (
    <div className="text-sm space-y-2">
      {card.pir && (
        <div>
          <span className="text-[10px] text-amber-400 uppercase font-semibold">PIR</span>
          <p className="text-foreground/80 mt-0.5">{card.pir}</p>
        </div>
      )}
      {card.branchId && (
        <div>
          <span className="text-[10px] text-muted-foreground uppercase font-semibold">Branch</span>
          <p className="text-foreground/60 mt-0.5 font-mono text-xs">{card.branchId}</p>
        </div>
      )}
    </div>
  )
}

export function NodeResultDetailModal({ card, open, onClose }: NodeResultDetailModalProps) {
  if (!card) return null
  const isIS = card.confidence !== undefined || !!card.pir

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-3 pr-8">
            <DialogTitle>{card.nodeName}</DialogTitle>
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                card.status === 'succeeded'
                  ? 'bg-green-950 text-green-400'
                  : card.status === 'failed'
                  ? 'bg-red-950 text-red-400'
                  : 'bg-amber-950 text-amber-400'
              }`}
            >
              {card.status}
            </span>
            {isIS && card.confidence !== undefined && (
              <div className="flex items-center gap-1.5 ml-auto">
                <div className="w-24 h-1.5 rounded bg-muted">
                  <div
                    className="h-1.5 rounded bg-violet-500"
                    style={{ width: `${Math.round(card.confidence * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] text-violet-400">
                  {Math.round(card.confidence * 100)}%
                </span>
              </div>
            )}
          </div>
        </DialogHeader>
        <DialogBody className="pt-4">
          <Tabs defaultValue="formatted">
            <TabsList className="mb-4">
              <TabsTrigger value="formatted">Formatted</TabsTrigger>
              {isIS && <TabsTrigger value="branch">Branch</TabsTrigger>}
              <TabsTrigger value="sources">Sources</TabsTrigger>
              <TabsTrigger value="raw">Raw Output</TabsTrigger>
            </TabsList>
            <TabsContent value="formatted">
              <FormattedTab card={card} />
            </TabsContent>
            {isIS && (
              <TabsContent value="branch">
                <BranchTab card={card} />
              </TabsContent>
            )}
            <TabsContent value="sources">
              <SourcesTab card={card} />
            </TabsContent>
            <TabsContent value="raw">
              <RawTab card={card} />
            </TabsContent>
          </Tabs>
        </DialogBody>
      </DialogContent>
    </Dialog>
  )
}
