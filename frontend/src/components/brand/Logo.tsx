import { LogoMark } from './LogoMark'

export type LogoSize = 'sm' | 'md' | 'lg'
export type LogoVariant = 'dark' | 'light'

export type LogoProps = {
  /** Size token. Default: "md". */
  size?: LogoSize
  /** Background variant the logo will sit on. Default: "dark". */
  variant?: LogoVariant
  /** If true, render mark only (no wordmark). Default: false. */
  markOnly?: boolean
  /** Show the "INTELLIGENCE PLATFORM" tagline. Default: true. */
  tagline?: boolean
  /** Optional className passthrough. */
  className?: string
}

// Size table from spec §3.4
const SIZE_MAP: Record<LogoSize, { markPx: number; wordmarkPx: number; taglinePx: number; gapPx: number }> = {
  sm: { markPx: 28, wordmarkPx: 15, taglinePx: 9,  gapPx: 10 },
  md: { markPx: 40, wordmarkPx: 20, taglinePx: 11, gapPx: 12 },
  lg: { markPx: 56, wordmarkPx: 28, taglinePx: 14, gapPx: 16 },
}

const FONT_STACK = "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"

export function Logo({
  size = 'md',
  variant = 'dark',
  markOnly = false,
  tagline = true,
  className,
}: LogoProps) {
  const { markPx, wordmarkPx, taglinePx, gapPx } = SIZE_MAP[size]

  // Wordmark is violet on both variants per spec §5.3/§5.4.
  // Tagline colour differs slightly: dark=slate, light=lighter slate.
  const wordmarkColor = 'var(--brand-violet)'
  const taglineColor = variant === 'light' ? 'var(--brand-tagline-light, #94a3b8)' : 'var(--brand-tagline)'

  return (
    <div
      role="img"
      aria-label="infobroker — Intelligence Platform"
      className={className}
      style={{
        display: 'inline-flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: gapPx,
      }}
    >
      <LogoMark size={markPx} />

      {!markOnly && (
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
          <span
            style={{
              fontFamily: FONT_STACK,
              fontWeight: 700,
              fontSize: wordmarkPx,
              letterSpacing: '-0.02em',
              color: wordmarkColor,
              lineHeight: 1,
            }}
          >
            infobroker
          </span>
          {tagline && (
            <span
              style={{
                fontFamily: FONT_STACK,
                fontWeight: 500,
                fontSize: taglinePx,
                letterSpacing: '0.18em',
                color: taglineColor,
                textTransform: 'uppercase',
                marginTop: `${wordmarkPx * 0.25}px`,
                lineHeight: 1,
              }}
            >
              Intelligence Platform
            </span>
          )}
        </div>
      )}
    </div>
  )
}
