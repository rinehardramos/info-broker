import React, { useState } from 'react'
import { useFindingGrade } from '@/hooks/useFindingGrade'

interface GradingRowProps {
  findingId: string
  runId: string
}

const GRADES = ['A', 'B', 'C', 'D'] as const
type Grade = (typeof GRADES)[number]

function timeAgo(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function GradingRow({ findingId, runId }: GradingRowProps) {
  const { myGrade, aggregate, isLoading, isSaving, save } = useFindingGrade(findingId, runId)
  const [selected, setSelected] = useState<Grade | null>(null)
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState(false)

  // If the user already has a grade and is not editing, show the saved state.
  if (myGrade && !editing) {
    return (
      <div className="mt-3 pt-3 border-t border-border/40 space-y-1.5">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground text-xs uppercase font-semibold tracking-wide">
            Grade
          </span>
          <span className="font-mono font-bold text-violet-400">{myGrade.grade}</span>
          <span className="text-muted-foreground text-xs">
            · {timeAgo(myGrade.graded_at)}
          </span>
          <button
            onClick={() => {
              setSelected(myGrade.grade as Grade)
              setNote(myGrade.note ?? '')
              setEditing(true)
            }}
            className="ml-auto text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Edit
          </button>
        </div>
        {aggregate && (
          <div className="text-[11px] text-muted-foreground">
            Aggregate: {aggregate.a_count}A · {aggregate.b_count}B · {aggregate.c_count}C ·{' '}
            {aggregate.d_count}D
          </div>
        )}
      </div>
    )
  }

  const canSave = selected !== null && !isSaving

  async function handleSave() {
    if (!selected) return
    await save(selected, note || undefined)
    setEditing(false)
  }

  return (
    <div className="mt-3 pt-3 border-t border-border/40 space-y-2">
      <p className="text-xs text-muted-foreground uppercase font-semibold tracking-wide">
        Grade this source
      </p>

      {/* Segmented control */}
      <div className="flex gap-1">
        {GRADES.map((g) => (
          <button
            key={g}
            onClick={() => setSelected(g)}
            disabled={isLoading}
            className={`w-9 h-8 rounded text-sm font-mono font-semibold transition-colors border ${
              selected === g
                ? 'bg-violet-600 border-violet-500 text-white'
                : 'bg-muted/40 border-border/60 text-muted-foreground hover:bg-muted/80 hover:text-foreground'
            }`}
          >
            {g}
          </button>
        ))}
      </div>

      {/* Optional note */}
      <input
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Your note (optional)"
        className="w-full text-xs bg-muted/30 border border-border/40 rounded px-2 py-1.5 text-foreground/80 placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-violet-500"
      />

      {/* Save / Cancel */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={!canSave}
          className="text-xs px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        {editing && (
          <button
            onClick={() => setEditing(false)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
        )}
      </div>

      {/* Aggregate (shown below controls) */}
      {aggregate && (
        <div className="text-[11px] text-muted-foreground">
          Aggregate: {aggregate.a_count}A · {aggregate.b_count}B · {aggregate.c_count}C ·{' '}
          {aggregate.d_count}D
        </div>
      )}
    </div>
  )
}
