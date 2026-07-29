import { PolarAngleAxis, PolarGrid, Radar, RadarChart as RechartsRadarChart, ResponsiveContainer } from 'recharts'

/**
 * Generic radar/spider chart over any real `Record<string, number>` (0-1 scores) — used for
 * ConfidenceBreakdownDto factors and SHAP feature-importance breakdowns. Never fed synthetic
 * axes; callers pass the actual backend field names/values through as-is.
 */
export function RadarChartCard({ data, labels, height = 260 }: { data: Record<string, number>; labels?: Record<string, string>; height?: number }) {
  const rows = Object.entries(data).map(([key, value]) => ({
    factor: labels?.[key] ?? key,
    value: Math.round(value * 100),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsRadarChart data={rows} outerRadius="75%">
        <PolarGrid stroke="var(--color-border-default)" />
        <PolarAngleAxis dataKey="factor" tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} />
        <Radar
          dataKey="value"
          stroke="var(--color-accent-primary)"
          fill="var(--color-accent-primary)"
          fillOpacity={0.25}
        />
      </RechartsRadarChart>
    </ResponsiveContainer>
  )
}
