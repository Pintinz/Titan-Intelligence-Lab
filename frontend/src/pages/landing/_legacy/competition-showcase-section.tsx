import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_COMPETITION_SPOTLIGHTS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

export function CompetitionShowcaseSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="competitions">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Competition intelligence</h2>
        <p className="mt-3 text-text-secondary">Every league TitanIQ covers, with predictions, teams, and news tracked in one place.</p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, margin: '-80px' }}
        className="-mx-1 mt-10 flex gap-6 overflow-x-auto px-1 pb-2 [scrollbar-width:none] sm:grid sm:overflow-visible sm:px-0 sm:pb-0 sm:grid-cols-2 lg:grid-cols-3 [&::-webkit-scrollbar]:hidden"
      >
        {SAMPLE_COMPETITION_SPOTLIGHTS.map((competition) => (
          <motion.div
            key={competition.id}
            variants={staggerItem}
            whileHover={{ y: -4 }}
            className="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)] sm:w-auto"
          >
            <div className="flex items-center gap-3">
              <TeamMonogramBadge id={competition.id} name={competition.name} size={40} />
              <div>
                <p className="font-display text-sm font-semibold text-text-primary">{competition.name}</p>
                <p className="text-xs text-text-muted">{competition.season} · {competition.country ?? 'International'}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              {competition.liveMatches > 0 && <Badge variant="danger">{competition.liveMatches} live</Badge>}
              <Badge variant="info">{competition.predictionsAvailable} predictions</Badge>
              <Badge variant="neutral">{competition.teamsCount} teams</Badge>
              <Badge variant="neutral">{competition.newsCount} news</Badge>
            </div>
            <p className="text-sm text-text-secondary">{competition.trendingStory}</p>
          </motion.div>
        ))}
      </motion.div>
    </section>
  )
}
