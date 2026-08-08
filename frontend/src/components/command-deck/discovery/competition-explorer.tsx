import type { CompetitionSummaryDto } from '@/lib/api/types'
import { CDLabel } from '../primitives/panel'

/**
 * CompetitionExplorer — replaces the plain `<select>` with real, scannable chips: each shows the
 * competition's own logo and how many of its fixtures fall in the window already loaded this
 * week (real count, not a fabricated "coverage" metric). Selecting a chip drives the same
 * `competitionId` filter state the section queries already read.
 */
export function CompetitionExplorer({
  competitions,
  fixtureCountByCompetition,
  liveCountByCompetition,
  selectedId,
  onSelect,
}: {
  competitions: CompetitionSummaryDto[]
  fixtureCountByCompetition: Record<string, number>
  liveCountByCompetition: Record<string, number>
  selectedId: string
  onSelect: (id: string) => void
}) {
  if (competitions.length === 0) return null

  return (
    <section>
      <CDLabel>Competitions</CDLabel>
      <div className="-mx-1 mt-2.5 flex gap-2 overflow-x-auto px-1 pb-1">
        <Chip label="All" active={selectedId === ''} onClick={() => onSelect('')} />
        {competitions.map((c) => (
          <Chip
            key={c.id}
            label={c.name}
            logoUrl={c.logo_url}
            count={fixtureCountByCompetition[c.id]}
            liveCount={liveCountByCompetition[c.id]}
            active={selectedId === c.id}
            onClick={() => onSelect(selectedId === c.id ? '' : c.id)}
          />
        ))}
      </div>
    </section>
  )
}

function Chip({
  label,
  logoUrl,
  count,
  liveCount,
  active,
  onClick,
}: {
  label: string
  logoUrl?: string | null
  count?: number
  liveCount?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="inline-flex shrink-0 items-center gap-2 rounded-full border py-1.5 pl-2 pr-3 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
      style={{
        borderColor: active ? 'var(--cd-accent)' : 'var(--cd-border-default)',
        backgroundColor: active ? 'var(--cd-accent-muted)' : 'var(--cd-surface-2)',
        color: active ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
      }}
    >
      {logoUrl ? (
        <img src={logoUrl} alt="" className="size-4 shrink-0 object-contain" loading="lazy" />
      ) : (
        <span className="size-4 shrink-0 rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }} aria-hidden="true" />
      )}
      <span className="whitespace-nowrap">{label}</span>
      {!!liveCount && (
        <span className="inline-flex items-center gap-1 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.04em]" style={{ color: 'var(--cd-live)' }}>
          <span className="size-1.5 animate-pulse rounded-full motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-live)' }} aria-hidden="true" />
          {liveCount}
        </span>
      )}
      {count !== undefined && count > 0 && (
        <span
          className="rounded-full px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[10px] tabular-nums"
          style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
        >
          {count}
        </span>
      )}
    </button>
  )
}
