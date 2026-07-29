import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'
import { TrendingUp, RefreshCw, Network, CheckCircle, AlertCircle, Zap } from 'lucide-react'

type Sport = 'football' | 'basketball' | 'baseball' | 'table-tennis'

const sports: Sport[] = ['football', 'basketball', 'baseball', 'table-tennis']

const sportMatches = {
  football: { home: 'Arsenal', away: 'Chelsea', confidence: 81, market: 'BTTS', pick: 'YES' },
  basketball: { home: 'Boston Celtics', away: 'Denver Nuggets', confidence: 74, market: 'Spread', pick: '-4.5' },
  baseball: { home: 'Dodgers', away: 'Giants', confidence: 88, market: 'Under', pick: '7.5' },
  'table-tennis': { home: 'Zhang', away: 'Ito', confidence: 69, market: 'Handicap', pick: '-2.5' },
}

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
  const [feedIndex, setFeedIndex] = useState(0)
  const match = sportMatches[currentSport]

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

        {/* Match Card */}
        <div className="relative w-full max-w-sm">
          <div className="absolute inset-0 bg-gradient-to-r from-accent-primary/20 to-premium/20 rounded-lg blur-lg" />
          <div className="relative border border-border-default/30 backdrop-blur-md bg-bg-secondary/40 rounded-lg p-4 space-y-3 hover:border-border-default/50 transition-all duration-300">
            <div className="flex items-center justify-between text-xs">
              <span className="font-telemetry uppercase tracking-wider text-text-muted">{currentSport}</span>
              <span className="font-telemetry text-accent-primary font-bold">{match.confidence}%</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="font-display font-semibold text-text-primary text-sm truncate">{match.home}</span>
              <span className="text-xs text-text-muted">vs</span>
              <span className="font-display font-semibold text-text-primary text-sm truncate">{match.away}</span>
            </div>
            <div className="flex items-center justify-between pt-2 border-t border-border-default/20">
              <span className="text-xs text-text-muted">{match.market}</span>
              <span className="font-telemetry font-medium text-accent-primary text-sm">{match.pick}</span>
            </div>
          </div>
        </div>

        {/* Confidence Bars */}
        <div className="space-y-2">
          {[match.confidence, match.confidence - 10, match.confidence + 8].map((conf, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs font-mono text-text-muted w-8">{conf}%</span>
              <div className="flex-1 h-1.5 bg-bg-secondary/50 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-accent-primary to-accent-primary-hover animate-pulse"
                  style={{
                    width: `${conf}%`,
                    animationDelay: `${i * 0.2}s`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Intelligence Feed */}
      <div className="relative z-10 space-y-2">
        {feedEvents.map((event, i) => {
          const Icon = event.icon
          const isActive = i === feedIndex
          return (
            <div
              key={i}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-500',
                isActive ? 'bg-bg-secondary/60 border border-border-default/30' : 'opacity-40'
              )}
            >
              <Icon className={cn('size-3', event.color)} />
              <span className="text-xs text-text-secondary">{event.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
