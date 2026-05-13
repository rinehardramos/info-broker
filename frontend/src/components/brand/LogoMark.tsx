export type LogoMarkProps = {
  size?: number
  color?: string
  className?: string
  title?: string
}

// Network graph mark — hub + 5 outer nodes + cross-connections between nodes.
// Rendered at 20px–48px; hub and outer nodes are similar size so it reads as
// a graph (not a star). Cross-edges between adjacent outer nodes make the
// network structure unmistakable.

const HUB = { cx: 32, cy: 32, r: 7 }

// 5 outer nodes, orbit radius 22, starting at top (270° = 12 o'clock)
const DEG_TO_RAD = Math.PI / 180
function polar(deg: number, r: number): { cx: number; cy: number } {
  const rad = (deg - 90) * DEG_TO_RAD   // -90 so 0° = top
  return { cx: +(32 + r * Math.cos(rad)).toFixed(2), cy: +(32 + r * Math.sin(rad)).toFixed(2) }
}
const ORBIT = 22
const OUTER = [
  { ...polar(0,   ORBIT), r: 5.5, opacity: 1.00 },   // top
  { ...polar(72,  ORBIT), r: 4.8, opacity: 0.90 },   // upper-right
  { ...polar(144, ORBIT), r: 4.2, opacity: 0.78 },   // lower-right
  { ...polar(216, ORBIT), r: 3.8, opacity: 0.68 },   // lower-left
  { ...polar(288, ORBIT), r: 4.5, opacity: 0.85 },   // upper-left
]

// Hub-to-node spokes — from hub edge to node edge
function spoke(node: typeof OUTER[0]) {
  const dx = node.cx - HUB.cx
  const dy = node.cy - HUB.cy
  const dist = Math.sqrt(dx * dx + dy * dy)
  const ux = dx / dist, uy = dy / dist
  return {
    x1: +(HUB.cx + ux * HUB.r).toFixed(2),
    y1: +(HUB.cy + uy * HUB.r).toFixed(2),
    x2: +(node.cx - ux * node.r).toFixed(2),
    y2: +(node.cy - uy * node.r).toFixed(2),
  }
}

// Cross-connections between adjacent outer nodes (0–1, 1–2, 3–4, 4–0)
// Skip 2–3 to leave a deliberate gap → asymmetry that reads as data flow
const CROSS_PAIRS: [number, number][] = [[0,1],[1,2],[3,4],[4,0]]
function crossEdge(a: typeof OUTER[0], b: typeof OUTER[0]) {
  const dx = b.cx - a.cx, dy = b.cy - a.cy
  const dist = Math.sqrt(dx * dx + dy * dy)
  const ux = dx / dist, uy = dy / dist
  return {
    x1: +(a.cx + ux * a.r).toFixed(2),
    y1: +(a.cy + uy * a.r).toFixed(2),
    x2: +(b.cx - ux * b.r).toFixed(2),
    y2: +(b.cy - uy * b.r).toFixed(2),
  }
}

export function LogoMark({ size = 32, color, className, title = 'infobroker' }: LogoMarkProps) {
  const fill   = color ?? 'var(--brand-violet, #a78bfa)'
  const stroke = color ?? 'var(--brand-violet, #a78bfa)'

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

      {/* Cross-connections between adjacent outer nodes */}
      {CROSS_PAIRS.map(([i, j], idx) => {
        const e = crossEdge(OUTER[i], OUTER[j])
        return (
          <line key={`cross-${idx}`}
            x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke={stroke} strokeWidth="1.2" strokeLinecap="round"
            opacity="0.28"
          />
        )
      })}

      {/* Hub-to-node spokes */}
      {OUTER.map((node, i) => {
        const s = spoke(node)
        return (
          <line key={`spoke-${i}`}
            x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
            stroke={stroke} strokeWidth="1.5" strokeLinecap="round"
            opacity={+(node.opacity * 0.65).toFixed(2)}
          />
        )
      })}

      {/* Outer nodes */}
      {OUTER.map((node, i) => (
        <circle key={`node-${i}`}
          cx={node.cx} cy={node.cy} r={node.r}
          fill={fill} opacity={node.opacity}
        />
      ))}

      {/* Central hub */}
      <circle cx={HUB.cx} cy={HUB.cy} r={HUB.r} fill={fill} />
    </svg>
  )
}
