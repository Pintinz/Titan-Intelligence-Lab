import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_PLAYER_SPOTLIGHTS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

const AVAILABILITY_VARIANT = { available: 'success', doubtful: 'warning', out: 'danger' } as const
const TREND_ICON = { up: TrendingUp, stable: Minus, down: TrendingDown }

export function PlayerSpotlightSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="players">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Player spotlight</h2>
        <p className="mt-3 text-text-secondary">Availability and performance trend — no crest or headshot data exists yet, so identity is a deterministic monogram, never a placeholder photo.</p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, margin: '-80px' }}
        className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
      >
        {SAMPLE_PLAYER_SPOTLIGHTS.map((player) => {
          const TrendIcon = TREND_ICON[player.performanceTrend]
          return (
            <motion.div
              key={player.id}
              variants={staggerItem}
              whileHover={{ y: -4 }}
              className="flex flex-col gap-3 rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)]"
            >
              <div className="flex items-center gap-3">
                <TeamMonogramBadge id={player.id} name={player.name} size={48} />
                <div>
                  <p className="font-display text-sm font-semibold text-text-primary">{player.name}</p>
                  <p className="text-xs text-text-muted">{player.position} · {player.team_name}</p>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs">
                <Badge variant={AVAILABILITY_VARIANT[player.availability]}>{player.availability}</Badge>
                <span className="flex items-center gap-1 text-text-secondary">
                  <TrendIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  {player.performanceTrend} trend
                </span>
              </div>
              <p className="text-sm text-text-secondary">{player.aiInsight}</p>
              <p className="font-mono text-xs text-text-muted">Prediction impact: {Math.round(player.predictionImpact * 100)}%</p>
            </motion.div>
          )
        })}
      </motion.div>
    </section>
  )
}
