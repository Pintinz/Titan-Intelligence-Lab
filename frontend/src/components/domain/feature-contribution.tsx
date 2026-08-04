import { cn } from '@/lib/cn'

interface Feature {
  name: string
  contribution: number // -1 to 1, where negative is opposing, positive is supporting
  strength: 'weak' | 'medium' | 'strong'
}

interface FeatureContributionProps {
  features: Feature[]
  className?: string
}

/**
 * Feature Contribution — shows which factors are driving the prediction.
 * Horizontal bars show supporting (positive, teal) vs opposing (negative, red) factors.
 * Explains model reasoning to users: "Why is this prediction 75% confident?"
 */
export function FeatureContribution({ features, className }: FeatureContributionProps) {
  if (!features || features.length === 0) {
    return (
      <div className={cn('flex items-center justify-center rounded-lg bg-bg-secondary p-4', className)}>
        <p className="text-xs text-text-muted">No feature data available</p>
      </div>
    )
  }

  const getColor = (contribution: number) => {
    if (contribution > 0) return 'bg-success'
    if (contribution < 0) return 'bg-danger'
    return 'bg-text-muted'
  }

  const getStrengthClass = (strength: 'weak' | 'medium' | 'strong') => {
    switch (strength) {
      case 'strong':
        return 'opacity-100'
      case 'medium':
        return 'opacity-75'
      case 'weak':
        return 'opacity-50'
    }
  }

  return (
    <div className={cn('space-y-3', className)}>
      {features.map((feature, i) => (
        <div key={i} className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted">{feature.name}</span>
            <span className={cn(
              'text-xs font-medium',
              feature.contribution > 0 && 'text-success',
              feature.contribution < 0 && 'text-danger',
              feature.contribution === 0 && 'text-text-muted',
            )}>
              {feature.contribution > 0 ? '+' : ''}{(feature.contribution * 100).toFixed(0)}%
            </span>
          </div>

          {/* Contribution bar — center-aligned */}
          <div className="flex h-2 overflow-hidden rounded-full bg-bg-primary">
            {/* Negative side (left) */}
            {feature.contribution < 0 && (
              <div
                className={cn(
                  'h-full transition-all duration-300',
                  getColor(feature.contribution),
                  getStrengthClass(feature.strength),
                )}
                style={{
                  width: `${Math.abs(feature.contribution) * 50}%`,
                }}
              />
            )}

            {/* Center spacer or positive offset */}
            {feature.contribution >= 0 && (
              <div className="h-full flex-1" />
            )}

            {/* Positive side (right) */}
            {feature.contribution > 0 && (
              <div
                className={cn(
                  'h-full transition-all duration-300',
                  getColor(feature.contribution),
                  getStrengthClass(feature.strength),
                )}
                style={{
                  width: `${feature.contribution * 50}%`,
                }}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
