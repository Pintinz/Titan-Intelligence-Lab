import { useId } from 'react'

/**
 * Momentum Curve — a filled area chart styled as a broadcast momentum-meter (the strip
 * shown under a football/basketball broadcast that leans toward whichever side is on
 * top). Positive values (home momentum) fill upward in the signal cyan; negative
 * (away momentum) fill downward in a muted rose — a shared zero-line, not two stacked
 * charts, so a shift in momentum reads as the fill crossing the center.
 */
export function InfinityMomentumCurve({ points, width = 320, height = 96 }: { points: number[]; width?: number; height?: number }) {
  // A static gradient id would collide the moment two curves render on the same page
  // (e.g. home vs away momentum side by side) — SVG ids are document-global, so the
  // second instance's <linearGradient> silently wins for both fills. useId() gives each
  // mounted instance its own id, stable across re-renders, safe under SSR.
  const gradientId = `infinity-momentum-pos-${useId()}`

  if (points.length < 2) return null
  const midY = height / 2
  const step = width / (points.length - 1)
  const scale = midY * 0.9

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${midY - Math.max(-1, Math.min(1, p)) * scale}`)
    .join(' ')
  const areaPath = `${path} L ${width} ${midY} L 0 ${midY} Z`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Momentum over time" className="w-full">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--infinity-signal)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--infinity-signal)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="0" y1={midY} x2={width} y2={midY} stroke="var(--infinity-border-hairline)" strokeWidth="1" />
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke="var(--infinity-signal)" strokeWidth="1.5" />
    </svg>
  )
}
