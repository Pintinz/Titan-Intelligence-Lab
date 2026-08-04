import { cn } from '@/lib/cn'
import {
  TrendingUp,
  AlertCircle,
  RefreshCw,
  CheckCircle,
  Zap,
  Network,
  BarChart3,
} from 'lucide-react'

export type IntelligenceFeedEventType =
  | 'prediction_updated'
  | 'confidence_recalibrated'
  | 'kg_updated'
  | 'learning_completed'
  | 'news_impact'
  | 'community_shift'
  | 'provider_synced'
  | 'model_evaluated'

interface IntelligenceFeedEventProps {
  type: IntelligenceFeedEventType
  title: string
  description?: string
  timestamp: string
  metadata?: Record<string, unknown>
  isNew?: boolean
}

const eventConfig: Record<IntelligenceFeedEventType, {
  icon: typeof TrendingUp
  bgColor: string
  iconColor: string
  label: string
}> = {
  prediction_updated: {
    icon: TrendingUp,
    bgColor: 'bg-accent-primary-muted',
    iconColor: 'text-accent-primary',
    label: 'Prediction Updated',
  },
  confidence_recalibrated: {
    icon: RefreshCw,
    bgColor: 'bg-accent-secondary-muted',
    iconColor: 'text-accent-secondary',
    label: 'Confidence Recalibrated',
  },
  kg_updated: {
    icon: Network,
    bgColor: 'bg-premium-muted',
    iconColor: 'text-premium',
    label: 'Knowledge Graph Updated',
  },
  learning_completed: {
    icon: CheckCircle,
    bgColor: 'bg-success-muted',
    iconColor: 'text-success',
    label: 'Learning Completed',
  },
  news_impact: {
    icon: AlertCircle,
    bgColor: 'bg-warning-muted',
    iconColor: 'text-warning',
    label: 'News Impact Detected',
  },
  community_shift: {
    icon: Zap,
    bgColor: 'bg-live-muted',
    iconColor: 'text-live',
    label: 'Community Shift',
  },
  provider_synced: {
    icon: BarChart3,
    bgColor: 'bg-info-muted',
    iconColor: 'text-info',
    label: 'Provider Synced',
  },
  model_evaluated: {
    icon: BarChart3,
    bgColor: 'bg-border-subtle',
    iconColor: 'text-text-secondary',
    label: 'Model Evaluated',
  },
}

export function IntelligenceFeedEvent({
  type,
  title,
  description,
  timestamp,
  metadata,
  isNew = false,
}: IntelligenceFeedEventProps) {
  const config = eventConfig[type]
  const Icon = config.icon

  return (
    <div
      className={cn(
        'group relative flex gap-3 border-l-2 border-border-subtle pl-4 py-3 transition-all duration-300 hover:border-accent-primary hover:bg-bg-secondary/50 rounded-r-lg',
        isNew && 'bg-bg-secondary/30 border-accent-primary',
      )}
    >
      {/* Live indicator for new events */}
      {isNew && (
        <div className="absolute -left-5 top-4 size-2 rounded-full bg-live animate-live-indicator" />
      )}

      {/* Icon badge */}
      <div className={cn('mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg', config.bgColor)}>
        <Icon className={cn('size-4', config.iconColor)} />
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-medium text-sm text-text-primary group-hover:text-accent-primary transition-colors">
              {title}
            </p>
            {description && (
              <p className="mt-0.5 text-xs text-text-secondary line-clamp-2">
                {description}
              </p>
            )}
          </div>
          <span className="font-mono text-xs text-text-muted flex-shrink-0">
            {timestamp}
          </span>
        </div>

        {/* Metadata tags */}
        {metadata && Object.entries(metadata).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(metadata).map(([key, value]) => (
              <span
                key={key}
                className="inline-block rounded bg-bg-primary px-2 py-0.5 text-xs text-text-muted"
              >
                {String(value)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
