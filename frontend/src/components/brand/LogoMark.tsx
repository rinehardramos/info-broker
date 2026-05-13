export type LogoMarkProps = {
  size?: number
  color?: string
  className?: string
  title?: string
}

// Network graph mark redesigned for clarity at all sizes.
// Key decisions:
//   - Hub r=9 (visible but not dominant)
//   - 5 outer nodes r=5–6 (substantial, clearly nodes not dots)
//   - Spoke lines stroke=2.5 + dashed secondary ring line for depth
//   - Cross-edges between 4 adjacent pairs at stroke=1.8
//   - Small accent dots at spoke midpoints to read as a data-flow network
//   - All geometry in 64×64 viewBox

const DEG_TO_RAD = Math.PI / 180
function polar(deg: number, r: number) {
  const a = (deg - 90) * DEG_TO_RAD
  return { cx: +(32 + r * Math.cos(a)).toFixed(2), cy: +(32 + r * Math.sin(a)).toFixed(2) }
}

const HUB_R = 9
const ORBIT = 22

// 5 outer nodes at 72° spacing, different radii for visual interest
const NODES = [
  { ...polar(0,   ORBIT), r: 6.0, op: 1.00 },   // top — anchor
  { ...polar(72,  ORBIT), r: 5.2, op: 0.88 },   // upper-right
  { ...polar(144, ORBIT), r: 4.5, op: 0.74 },   // lower-right
  { ...polar(216, ORBIT), r: 4.0, op: 0.62 },   // lower-left
  { ...polar(288, ORBIT), r: 5.0, op: 0.82 },   // upper-left
]

// Spoke from hub-edge to node-edge
function spoke(node: typeof NODES[0]) {
  const dx = node.cx - 32, dy = node.cy - 32
  const d = Math.sqrt(dx * dx + dy * dy)
  const ux = dx / d, uy = dy / d
  return {
    x1: +(32 + ux * HUB_R).toFixed(2),  y1: +(32 + uy * HUB_R).toFixed(2),
    x2: +(node.cx - ux * node.r).toFixed(2), y2: +(node.cy - uy * node.r).toFixed(2),
  }
}

// Midpoint of a spoke (for accent dot)
function spokeMid(node: typeof NODES[0]) {
  const s = spoke(node)
  return { cx: +((+s.x1 + +s.x2) / 2).toFixed(2), cy: +((+s.y1 + +s.y2) / 2).toFixed(2) }
}

// Cross-edge between two adjacent outer nodes (edge-to-edge)
function cross(a: typeof NODES[0], b: typeof NODES[0]) {
  const dx = b.cx - a.cx, dy = b.cy - a.cy
  const d = Math.sqrt(dx * dx + dy * dy)
  const ux = dx / d, uy = dy / d
  return {
    x1: +(a.cx + ux * a.r).toFixed(2), y1: +(a.cy + uy * a.r).toFixed(2),
    x2: +(b.cx - ux * b.r).toFixed(2), y2: +(b.cy - uy * b.r).toFixed(2),
  }
}

// Adjacent pairs — skip 2↔3 to create intentional gap (asymmetry = dynamic)
const CROSS_PAIRS: [number, number][] = [[0,1],[1,2],[3,4],[4,0]]

export function LogoMark({ size = 32, color, className, title = 'infobroker' }: LogoMarkProps) {
  const c = color ?? 'var(--brand-violet, #a78bfa)'

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

      {/* ── Layer 1: subtle orbit ring (dashed) ── */}
      <circle
        cx="32" cy="32" r={ORBIT}
        fill="none" stroke={c} strokeWidth="0.6"
        strokeDasharray="2.5 3.5" opacity="0.18"
      />

      {/* ── Layer 2: cross-edges between adjacent nodes ── */}
      {CROSS_PAIRS.map(([i, j], k) => {
        const e = cross(NODES[i], NODES[j])
        return (
          <line key={`x${k}`}
            x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke={c} strokeWidth="1.6" strokeLinecap="round"
            opacity="0.36"
          />
        )
      })}

      {/* ── Layer 3: hub spokes — thick, high-contrast ── */}
      {NODES.map((node, i) => {
        const s = spoke(node)
        return (
          <line key={`s${i}`}
            x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
            stroke={c} strokeWidth="2.5" strokeLinecap="round"
            opacity={+(node.op * 0.75).toFixed(2)}
          />
        )
      })}

      {/* ── Layer 4: accent dots at spoke midpoints ── */}
      {NODES.map((node, i) => {
        const m = spokeMid(node)
        return (
          <circle key={`m${i}`}
            cx={m.cx} cy={m.cy} r="1.4"
            fill={c} opacity={+(node.op * 0.55).toFixed(2)}
          />
        )
      })}

      {/* ── Layer 5: outer nodes ── */}
      {NODES.map((node, i) => (
        <circle key={`n${i}`}
          cx={node.cx} cy={node.cy} r={node.r}
          fill={c} opacity={node.op}
        />
      ))}

      {/* ── Layer 6: hub — glowing ring + fill ── */}
      <circle cx="32" cy="32" r={HUB_R + 2.5}
        fill="none" stroke={c} strokeWidth="1.2" opacity="0.22"
      />
      <circle cx="32" cy="32" r={HUB_R}
        fill={c}
      />
    </svg>
  )
}
