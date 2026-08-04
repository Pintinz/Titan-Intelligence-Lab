/**
 * Heatmap — used for pitch/court zone intensity and calendar-style activity grids.
 * Cell color interpolates through the signal cyan (not a rainbow scale) so every
 * heatmap in the system reads as "belongs to TitanIQ," never a generic d3 default.
 */
export function InfinityHeatmap({
  rows,
  cols,
  values,
  cellSize = 28,
}: {
  rows: number
  cols: number
  values: number[]
  /** Pixel size per cell — a CSS grid with `1fr` tracks and no intrinsic content has no
   * width to derive from, so this must be explicit rather than left to `aspect-square`. */
  cellSize?: number
}) {
  return (
    <div
      className="grid gap-0.5"
      style={{
        gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`,
        gridTemplateRows: `repeat(${rows}, ${cellSize}px)`,
      }}
      role="img"
      aria-label="Intensity heatmap"
    >
      {values.map((v, i) => {
        const intensity = Math.max(0, Math.min(1, v))
        return (
          <div
            key={i}
            className="rounded-[2px]"
            style={{ backgroundColor: `rgba(0, 209, 255, ${0.06 + intensity * 0.75})` }}
            title={`${Math.round(intensity * 100)}%`}
          />
        )
      })}
    </div>
  )
}
