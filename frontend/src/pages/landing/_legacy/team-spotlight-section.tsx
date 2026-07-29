import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_TEAM_SPOTLIGHTS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

export function TeamSpotlightSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="teams">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Team spotlight</h2>
        <p className="mt-3 text-text-secondary">Form, power ranking, and prediction strength — the signals behind every team-level forecast.</p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, margin: '-80px' }}
        className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
      >
        {SAMPLE_TEAM_SPOTLIGHTS.map((team) => (
          <motion.div
            key={team.id}
            variants={staggerItem}
            whileHover={{ y: -4 }}
            className="flex flex-col gap-3 rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)]"
          >
            <div className="flex items-center gap-3">
              <TeamMonogramBadge id={team.id} name={team.short_name} size={48} />
              <div>
                <p className="font-display text-sm font-semibold text-text-primary">{team.name}</p>
                <p className="font-mono text-xs text-text-muted">Power rank #{team.powerRanking}</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs text-text-secondary">
              <span>Form <span className="font-mono text-text-primary">{team.recentForm}</span></span>
              <Badge variant="accent">{Math.round(team.predictionStrength * 100)}% strength</Badge>
            </div>
            <p className="text-sm text-text-secondary">{team.aiSummary}</p>
            <p className="text-xs text-text-muted">Next: {team.upcomingOpponent}</p>
          </motion.div>
        ))}
      </motion.div>
    </section>
  )
}
