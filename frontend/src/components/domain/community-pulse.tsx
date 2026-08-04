import { cn } from '@/lib/cn'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface PulseMetric {
  label: string
  value: number
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: number
  max?: number
}

interface CommunityPulseProps {
  metrics: PulseMetric[]
  className?: string
}

/**
 * Community Pulse — visualizes community signals with:
 * - Activity level bars
 * - Sentiment distribution
 * - Trend indicators
 * Shows community movement and collective intelligence in real time
 */
export function CommunityPulse({ metrics, className }: CommunityPulseProps) {
  if (!metrics || metrics.length === 0) {
    return (
      <div className={cn('flex items-center justify-center rounded-lg bg-bg-secondary p-4', className)}>
        <p className="text-xs text-text-muted">No community signals</p>
      </div>
    )
  }

  const maxValue = Math.max(...metrics.map((m) => m.max || m.value))

  return (
    <div className={cn('space-y-3', className)}>
      {metrics.map((metric, i) => (
        <div key={i} className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted">{metric.label}</span>
            <div className="flex items-center gap-1">
              <span className="font-telemetry text-sm font-semibold text-text-primary">
                {metric.value}
              </span>
              {metric.trend && metric.trendValue !== undefined && (
                <span
                  className={cn(
                    'flex items-center gap-0.5 text-xs font-medium',
                    metric.trend === 'up' && 'text-success',
                    metric.trend === 'down' && 'text-danger',
                    metric.trend === 'neutral' && 'text-text-muted',
                  )}
                >
                  {metric.trend === 'up' && <TrendingUp className="size-3" />}
                  {metric.trend === 'down' && <TrendingDown className="size-3" />}
                  {Math.abs(metric.trendValue)}%
                </span>
              )}
            </div>
          </div>

          {/* Activity bar with pulse animation */}
          <div className="relative h-2 overflow-hidden rounded-full bg-bg-primary">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500 animate-confidence-pulse',
                'bg-gradient-to-r from-accent-primary to-accent-primary/70',
              )}
              style={{
                width: `${(metric.value / (maxValue || 100)) * 100}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
