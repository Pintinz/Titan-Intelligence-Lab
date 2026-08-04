/**
 * Prediction Evolution — a step-line (not smoothed) showing how a prediction's
 * probability moved as evidence arrived, with a marker at every point evidence changed
 * it (news, KG update, model retrain). The step (not curve) shape is deliberate: a
 * prediction changes in discrete jumps when new evidence lands, never gradually.
 */
export function InfinityPredictionEvolution({
  points,
  width = 320,
  height = 100,
}: {
  points: Array<{ value: number; label: string }>
  width?: number
  height?: number
}) {
  if (points.length < 2) return null
  const step = width / (points.length - 1)
  const y = (v: number) => height - v * height * 0.85 - height * 0.05

  const stepPath = points
    .map((p, i) => {
      if (i === 0) return `M 0 ${y(p.value)}`
      const prevX = (i - 1) * step
      return `L ${prevX + step} ${y(points[i - 1].value)} L ${i * step} ${y(p.value)}`
    })
    .join(' ')

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Prediction evolution over time" className="w-full">
      <path d={stepPath} fill="none" stroke="var(--infinity-domain-predictions)" strokeWidth="1.5" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={i * step} cy={y(p.value)} r="2.5" fill="var(--infinity-ground-0)" stroke="var(--infinity-domain-predictions)" strokeWidth="1.5" />
      ))}
    </svg>
  )
}
