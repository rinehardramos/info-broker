import { useState } from 'react'

const SOURCE_COLORS: Record<string, string> = {
  A: '#22c55e',
  B: '#4ade80',
  C: '#facc15',
  D: '#fb923c',
  E: '#f87171',
  F: '#6b7280',
}

const SOURCE_LABELS: Record<string, string> = {
  A: 'Completely reliable',
  B: 'Usually reliable',
  C: 'Fairly reliable',
  D: 'Not usually reliable',
  E: 'Unreliable',
  F: 'Cannot be judged',
}

const CRED_LABELS: Record<string, string> = {
  '1': 'Confirmed by other sources',
  '2': 'Probably true',
  '3': 'Possibly true',
  '4': 'Doubtful',
  '5': 'Improbable',
  '6': 'Cannot be judged',
}

function parseGrade(grade: string | null | undefined): [string, string] {
  if (!grade) return ['F', '6']
  if (grade.length === 2 && 'ABCDEF'.includes(grade[0]) && '123456'.includes(grade[1]))
    return [grade[0], grade[1]]
  if (grade.length === 1 && 'ABCDEF'.includes(grade[0]))
    return [grade[0], '3']
  return ['F', '6']
}

interface GradeBadgeProps {
  autoGrade: string
  userGrade: string | null
  onGrade: (grade: string) => void
  size?: 'sm' | 'md'
}

export function GradeBadge({ autoGrade, userGrade, onGrade, size = 'sm' }: GradeBadgeProps) {
  const [open, setOpen] = useState(false)
  const [pendingSrc, setPendingSrc] = useState<string | null>(null)
  const [pendingCred, setPendingCred] = useState<string | null>(null)

  const displayGrade = userGrade || autoGrade
  const [src, cred] = parseGrade(displayGrade)

  const color = SOURCE_COLORS[src] || '#6b7280'
  const dim = size === 'sm' ? 26 : 34
  const fontSize = size === 'sm' ? 10 : 12

  const tooltip = [
    `Admiralty: ${displayGrade}`,
    `Source: ${SOURCE_LABELS[src] ?? src}`,
    `Info: ${CRED_LABELS[cred] ?? cred}`,
    userGrade ? `Auto: ${autoGrade}` : '',
    'Click to manually grade',
  ].filter(Boolean).join('\n')

  function handleApply() {
    const s = pendingSrc ?? src
    const c = pendingCred ?? cred
    onGrade(s + c)
    setOpen(false)
    setPendingSrc(null)
    setPendingCred(null)
  }

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen(o => !o)}
        title={tooltip}
        style={{
          width: dim, height: dim,
          background: color + '22',
          border: `1.5px solid ${color}`,
          borderRadius: 5,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer',
          gap: 1,
          padding: '0 3px',
          transition: 'all 0.15s',
          outline: userGrade ? `2px solid ${color}` : 'none',
          outlineOffset: 1,
        }}
      >
        <span style={{ fontSize, fontWeight: 700, color, lineHeight: 1 }}>{src}</span>
        <span style={{ fontSize: fontSize - 2, fontWeight: 600, color: color + 'bb', lineHeight: 1 }}>{cred}</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute', zIndex: 200, top: dim + 4, left: 0,
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: 8,
            padding: 10,
            minWidth: 230,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          }}
        >
          {/* Source */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 9, color: '#64748b', fontWeight: 700, marginBottom: 4, letterSpacing: '0.08em' }}>
              SOURCE RELIABILITY
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {['A', 'B', 'C', 'D', 'E', 'F'].map(s => {
                const active = (pendingSrc ?? src) === s
                return (
                  <button
                    key={s}
                    onClick={() => setPendingSrc(s)}
                    title={SOURCE_LABELS[s]}
                    style={{
                      width: 28, height: 28,
                      background: active ? SOURCE_COLORS[s] + '33' : 'transparent',
                      border: `1.5px solid ${active ? SOURCE_COLORS[s] : '#1e293b'}`,
                      borderRadius: 4,
                      color: SOURCE_COLORS[s],
                      fontSize: 11, fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {s}
                  </button>
                )
              })}
            </div>
            <div style={{ fontSize: 9, color: '#475569', marginTop: 3 }}>
              {SOURCE_LABELS[pendingSrc ?? src]}
            </div>
          </div>

          {/* Credibility */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 9, color: '#64748b', fontWeight: 700, marginBottom: 4, letterSpacing: '0.08em' }}>
              INFORMATION CREDIBILITY
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {['1', '2', '3', '4', '5', '6'].map(n => {
                const active = (pendingCred ?? cred) === n
                const sc = SOURCE_COLORS[pendingSrc ?? src]
                return (
                  <button
                    key={n}
                    onClick={() => setPendingCred(n)}
                    title={CRED_LABELS[n]}
                    style={{
                      width: 28, height: 28,
                      background: active ? sc + '33' : 'transparent',
                      border: `1.5px solid ${active ? sc : '#1e293b'}`,
                      borderRadius: 4,
                      color: active ? sc : '#475569',
                      fontSize: 11, fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {n}
                  </button>
                )
              })}
            </div>
            <div style={{ fontSize: 9, color: '#475569', marginTop: 3 }}>
              {CRED_LABELS[pendingCred ?? cred]}
            </div>
          </div>

          {/* Preview + apply */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>
              {'→ '}
              <span style={{ fontWeight: 700, color: SOURCE_COLORS[pendingSrc ?? src] }}>
                {(pendingSrc ?? src)}{(pendingCred ?? cred)}
              </span>
              {' — '}
              <span style={{ fontSize: 9, color: '#64748b' }}>
                {SOURCE_LABELS[pendingSrc ?? src].split(' ')[0].toLowerCase()}
              </span>
            </span>
            <button
              onClick={handleApply}
              style={{
                background: SOURCE_COLORS[pendingSrc ?? src],
                color: '#000', border: 'none',
                fontSize: 10, fontWeight: 700,
                padding: '4px 14px', borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
