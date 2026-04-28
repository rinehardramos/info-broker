import { useState } from 'react'

const GRADES = [
  { key: 'target',      label: 'Target',      icon: '🎯' },
  { key: 'interesting', label: 'Interesting',  icon: '💡' },
  { key: 'amazing',     label: 'Amazing',      icon: '⭐' },
  { key: 'not_close',   label: 'Not close',    icon: '✗' },
  { key: 'undecided',   label: 'Undecided',    icon: '·' },
] as const

type GradeKey = typeof GRADES[number]['key']

interface Props {
  resultId: string
  jobId: string
  initialGrade: string | null
  onGrade: (resultId: string, grade: string) => void
}

export default function GradeBar({ resultId, jobId, initialGrade, onGrade }: Props) {
  const [active, setActive] = useState<string | null>(initialGrade)

  function handleClick(grade: GradeKey) {
    setActive(grade)
    onGrade(resultId, grade)
  }

  return (
    <div className="flex gap-1 mt-2 flex-wrap">
      {GRADES.map(g => {
        const isActive = active === g.key
        return (
          <button
            key={g.key}
            title={g.label}
            onClick={() => handleClick(g.key)}
            className="px-2 py-0.5 rounded text-[10px] transition-colors"
            style={{
              background: isActive ? 'var(--accent)' : 'var(--panel)',
              color:      isActive ? 'var(--bg)'     : 'var(--muted)',
              border:     `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
              cursor: 'pointer',
            }}
          >
            {g.icon} {g.label}
          </button>
        )
      })}
    </div>
  )
}
