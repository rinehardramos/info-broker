export type LogoMarkProps = {
  /** Pixel size of the square mark. Default: 32. */
  size?: number
  /** Override the mark colour. Defaults to var(--brand-violet). */
  color?: string
  /** Optional className passthrough. */
  className?: string
  /** Optional ARIA label. Default: "infobroker". */
  title?: string
}

// Geometry: hub at (32,32), orbit radius 24, 5 satellites at 72° from top.
// Exact coordinates from the spec §2.2 and §2.3.
const SATELLITES = [
  { cx: 32.00, cy: 8.00,  r: 4.0, opacity: 1.00 },
  { cx: 54.83, cy: 24.58, r: 3.4, opacity: 0.85 },
  { cx: 46.11, cy: 51.41, r: 2.8, opacity: 0.70 },
  { cx: 17.89, cy: 51.41, r: 2.4, opacity: 0.55 },
  { cx: 9.17,  cy: 24.58, r: 3.0, opacity: 0.78 },
]

const LINES = [
  { x1: 32.00, y1: 22.00, x2: 32.00, y2: 12.00, opacity: 0.55 },
  { x1: 41.51, y1: 28.91, x2: 51.60, y2: 25.65, opacity: 0.45 },
  { x1: 37.88, y1: 40.09, x2: 44.46, y2: 44.85, opacity: 0.40 },
  { x1: 26.12, y1: 40.09, x2: 19.59, y2: 44.85, opacity: 0.35 },
  { x1: 22.49, y1: 28.91, x2: 12.40, y2: 25.65, opacity: 0.45 },
]

export function LogoMark({ size = 32, color, className, title = 'infobroker' }: LogoMarkProps) {
  const fill = color ?? 'var(--brand-violet)'
  const stroke = color ?? 'var(--brand-violet)'

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>

      {/* 1. Connector lines (bottom layer) */}
      {LINES.map((l, i) => (
        <line
          key={i}
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          stroke={stroke}
          strokeWidth="1.25"
          strokeLinecap="round"
          opacity={l.opacity}
        />
      ))}

      {/* 2. Satellite circles (middle layer) */}
      {SATELLITES.map((s, i) => (
        <circle
          key={i}
          cx={s.cx}
          cy={s.cy}
          r={s.r}
          fill={fill}
          opacity={s.opacity}
        />
      ))}

      {/* 3. Central hub (top layer) */}
      <circle cx="32" cy="32" r="10" fill={fill} />
    </svg>
  )
}
