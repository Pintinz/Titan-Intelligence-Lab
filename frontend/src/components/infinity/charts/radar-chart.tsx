/**
 * Radar — used for player/team attribute comparison. Styled as a targeting
 * reticle (concentric rings + crosshair spokes) rather than a filled polygon-only
 * radar, so it reads as "evidence overlay" not a generic gaming stat wheel.
 */
export function InfinityRadarChart({
  axes,
  values,
  size = 200,
  tone = 'var(--infinity-signal)',
}: {
  axes: string[]
  values: number[]
  size?: number
  tone?: string
}) {
  const center = size / 2
  const radius = size * 0.36
  const angleFor = (i: number) => (Math.PI * 2 * i) / axes.length - Math.PI / 2

  const point = (i: number, scale: number) => {
    const angle = angleFor(i)
    return [center + Math.cos(angle) * radius * scale, center + Math.sin(angle) * radius * scale]
  }

  const polygon = values.map((v, i) => point(i, Math.max(0, Math.min(1, v))).join(',')).join(' ')

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Attribute radar">
      {[0.33, 0.66, 1].map((ring) => (
        <circle key={ring} cx={center} cy={center} r={radius * ring} fill="none" stroke="var(--infinity-border-hairline)" strokeWidth="1" />
      ))}
      {axes.map((_, i) => {
        const [x, y] = point(i, 1)
        return <line key={`spoke-${i}`} x1={center} y1={center} x2={x} y2={y} stroke="var(--infinity-border-hairline)" strokeWidth="1" />
      })}
      <polygon points={polygon} fill={tone} fillOpacity="0.18" stroke={tone} strokeWidth="1.5" />
      {values.map((v, i) => {
        const [x, y] = point(i, Math.max(0, Math.min(1, v)))
        return <circle key={`point-${i}`} cx={x} cy={y} r="2.5" fill={tone} />
      })}
      {axes.map((label, i) => {
        const [x, y] = point(i, 1.22)
        return (
          <text
            key={label}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-infinity-text-muted font-infinity-body"
            style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em' }}
          >
            {label}
          </text>
        )
      })}
    </svg>
  )
}
