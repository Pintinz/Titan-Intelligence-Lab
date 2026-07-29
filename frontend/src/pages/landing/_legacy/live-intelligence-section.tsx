import { motion } from 'framer-motion'
import { Radio, TrendingUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_FIXTURES, SAMPLE_ALERTS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

const STATUS_LABEL: Record<string, string> = { live: 'Live', scheduled: 'Upcoming', finished: 'Finished' }
const STATUS_VARIANT: Record<string, 'danger' | 'info' | 'neutral'> = { live: 'danger', scheduled: 'info', finished: 'neutral' }

export function LiveIntelligenceSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="live-intelligence">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.2em] text-danger">
            <Radio className="h-3 w-3 animate-pulse" aria-hidden="true" />
            Live sports intelligence
          </span>
          <h2 className="mt-2 font-display text-3xl font-semibold text-text-primary">
            What TitanIQ is tracking right now
          </h2>
        </div>
        <p className="max-w-sm text-sm text-text-muted">
          Illustrative — reflects the realtime channels (matches, predictions, provider incidents) every
          signed-in user subscribes to; sign in to see this feed live.
        </p>
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <motion.div
          variants={staggerContainer}
          initial="initial"
          whileInView="animate"
          viewport={{ once: true, margin: '-80px' }}
          className="-mx-1 flex gap-4 overflow-x-auto px-1 pb-2 [scrollbar-width:none] lg:grid lg:grid-cols-2 lg:overflow-visible [&::-webkit-scrollbar]:hidden"
        >
          {SAMPLE_FIXTURES.map((fixture) => (
            <motion.div
              key={fixture.id}
              variants={staggerItem}
              whileHover={{ y: -3 }}
              className="w-64 shrink-0 rounded-lg border border-border-default bg-bg-elevated p-4 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-2)] lg:w-auto"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-text-muted">{fixture.competition_name}</span>
                <Badge variant={STATUS_VARIANT[fixture.status] ?? 'neutral'}>{STATUS_LABEL[fixture.status] ?? fixture.status}</Badge>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <TeamRow id={fixture.home_team.id} name={fixture.home_team.short_name} />
                <span className="font-mono text-xs text-text-muted">vs</span>
                <TeamRow id={fixture.away_team.id} name={fixture.away_team.short_name} />
              </div>
            </motion.div>
          ))}
        </motion.div>

        <div className="flex flex-col gap-3">
          <span className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-text-muted">
            <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
            AI alerts
          </span>
          {SAMPLE_ALERTS.map((alert) => (
            <div key={alert.label} className="rounded-md border border-border-subtle bg-bg-secondary/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-text-primary">{alert.label}</span>
                <Badge variant={alert.tone}>{alert.tone}</Badge>
              </div>
              <p className="mt-1 text-xs text-text-secondary">{alert.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function TeamRow({ id, name }: { id: string; name: string }) {
  return (
    <span className="flex flex-1 flex-col items-center gap-1 text-center">
      <TeamMonogramBadge id={id} name={name} size={32} />
      <span className="font-mono text-xs text-text-secondary">{name}</span>
    </span>
  )
}
