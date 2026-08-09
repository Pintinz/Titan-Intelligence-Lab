import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'
import { TrendingUp, RefreshCw, Network, CheckCircle, AlertCircle, Zap } from 'lucide-react'

type Sport = 'football' | 'basketball' | 'baseball' | 'table-tennis'

const sports: Sport[] = ['football', 'basketball', 'baseball', 'table-tennis']

const sportLabels: Record<Sport, string> = {
  football: 'Football',
  basketball: 'Basketball',
  baseball: 'Baseball',
  'table-tennis': 'Table Tennis',
}

/** Real, evergreen platform mechanisms (PRODUCT.md "Evidence on Hand") — never a specific match,
 * score, or confidence number, since no sports/prediction data is reachable before authentication
 * (every real endpoint requires a session). True regardless of which sport is showing, so this
 * never overclaims coverage a given sport doesn't have yet. */
const capabilities = [
  { icon: TrendingUp, title: 'Explainable predictions', detail: 'Every verdict traces to real SHAP-based feature evidence, never a black box.' },
  { icon: Network, title: 'Knowledge Graph', detail: 'Teams, players, and competitions connected through a real relationship graph.' },
  { icon: RefreshCw, title: 'Confidence engine', detail: 'A 9-factor composite score grounded in feature quality, freshness, and model reliability.' },
  { icon: CheckCircle, title: 'Continuous learning', detail: 'Models recalibrate on a scheduled loop against real resolved outcomes.' },
]

const feedEvents = [
  { icon: TrendingUp, label: 'Prediction Updated', color: 'text-accent-primary' },
  { icon: RefreshCw, label: 'Confidence Recalibrated', color: 'text-accent-secondary' },
  { icon: Network, label: 'Knowledge Graph Updated', color: 'text-premium' },
  { icon: CheckCircle, label: 'Learning Pipeline Complete', color: 'text-success' },
  { icon: AlertCircle, label: 'News Impact Detected', color: 'text-warning' },
  { icon: Zap, label: 'Community Shift Detected', color: 'text-live' },
]

export function IntelligenceCanvas() {
  const [currentSport, setCurrentSport] = useState<Sport>('football')
  const [capabilityIndex, setCapabilityIndex] = useState(0)
  const [feedIndex, setFeedIndex] = useState(0)
  const capability = capabilities[capabilityIndex]
  const Icon = capability.icon

  useEffect(() => {
    const sportInterval = setInterval(() => {
      setCurrentSport((prev) => {
        const idx = sports.indexOf(prev)
        return sports[(idx + 1) % sports.length]
      })
    }, 10000)

    return () => clearInterval(sportInterval)
  }, [])

  useEffect(() => {
    const capabilityInterval = setInterval(() => {
      setCapabilityIndex((prev) => (prev + 1) % capabilities.length)
    }, 6000)

    return () => clearInterval(capabilityInterval)
  }, [])

  useEffect(() => {
    const feedInterval = setInterval(() => {
      setFeedIndex((prev) => (prev + 1) % feedEvents.length)
    }, 5000)

    return () => clearInterval(feedInterval)
  }, [])

  return (
    <div className="hidden lg:flex relative h-full flex-col justify-between overflow-hidden bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary p-8">
      {/* Animated background gradient */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-accent-primary rounded-full mix-blend-screen filter blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-premium rounded-full mix-blend-screen filter blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      {/* Content */}
      <div className="relative z-10 space-y-8">
        {/* Branding */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="inline-block size-2.5 rounded-full bg-accent-primary animate-pulse" />
            <h1 className="font-display text-3xl font-bold text-text-primary">TitanIQ</h1>
          </div>
          <p className="text-sm font-medium text-accent-primary">See Every Match Through Intelligence.</p>
          <p className="text-xs text-text-secondary max-w-md leading-relaxed">
            TitanIQ transforms live sports data, structured intelligence, news, community signals, and machine learning into explainable sports intelligence. Predictions are only one output. Everything is backed by evidence.
          </p>
        </div>

        {/* Capability Card — real platform mechanisms, never a fabricated match or score */}
        <div className="relative w-full max-w-sm">
          <div className="absolute inset-0 bg-gradient-to-r from-accent-primary/20 to-premium/20 rounded-lg blur-lg" />
          <div className="relative border border-border-default/30 backdrop-blur-md bg-bg-secondary/40 rounded-lg p-4 space-y-3 hover:border-border-default/50 transition-all duration-300">
            <div className="flex items-center justify-between text-xs">
              <span className="font-telemetry uppercase tracking-wider text-text-muted">{sportLabels[currentSport]}</span>
              <span className="font-telemetry text-accent-primary font-bold uppercase tracking-wider">Live intelligence</span>
            </div>
            <div className="flex items-center gap-2.5">
              <Icon className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
              <span className="font-display font-semibold text-text-primary text-sm">{capability.title}</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">{capability.detail}</p>
          </div>
        </div>
      </div>

      {/* Intelligence Feed */}
      <div className="relative z-10 space-y-2">
        {feedEvents.map((event, i) => {
          const FeedIcon = event.icon
          const isActive = i === feedIndex
          return (
            <div
              key={i}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-500',
                isActive ? 'bg-bg-secondary/60 border border-border-default/30' : 'opacity-40'
              )}
            >
              <FeedIcon className={cn('size-3', event.color)} />
              <span className="text-xs text-text-secondary">{event.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
