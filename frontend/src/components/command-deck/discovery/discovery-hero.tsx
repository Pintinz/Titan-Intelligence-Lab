import { Search, Star } from 'lucide-react'
import { CDPanel } from '../primitives/panel'
import { CDTelemetryValue } from '../primitives/telemetry'
import type { SportMeta } from '@/lib/hooks/use-sport'

export interface DiscoveryKpis {
  live: number | null
  today: number | null
  thisWeek: number | null
  aiMarkets: number | null
  competitions: number | null
}

/**
 * DiscoveryHero — a compact, functional opening instrument for the Match Discovery & Intelligence
 * Center. Operate mode, not Persuade: no cinematic imagery, no invented eyebrow above the heading
 * (SportShell already carries "Intelligence Center / {Sport}" directly above this). Every KPI
 * traces to a real query result the page already fetches — a sport with zero production markets
 * reads "0" honestly rather than hiding the tile.
 */
export function DiscoveryHero({
  sport,
  search,
  onSearchChange,
  followingOnly,
  onToggleFollowingOnly,
  kpis,
}: {
  sport: SportMeta
  search: string
  onSearchChange: (value: string) => void
  followingOnly: boolean
  onToggleFollowingOnly: () => void
  kpis: DiscoveryKpis
}) {
  return (
    <CDPanel className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 opacity-50"
        style={{ background: 'radial-gradient(110% 90% at 15% -10%, var(--cd-accent-muted), transparent 60%)' }}
        aria-hidden="true"
      />

      <div className="relative flex flex-col gap-5">
        <div className="min-w-0">
          <h2 className="font-[var(--cd-font-display)] text-xl font-semibold sm:text-2xl" style={{ color: 'var(--cd-text-primary)' }}>
            Everything live and upcoming in {sport.label}
          </h2>
          <p className="mt-1.5 max-w-md font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            Browse what's live, what's coming up, and every competition under TitanIQ coverage — then generate AI intelligence on demand.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
              <input
                type="search"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search team or competition"
                className="h-9 w-full rounded-[var(--cd-radius-md)] border pl-8 pr-3 font-[var(--cd-font-body)] text-[13px] outline-none transition-colors duration-[var(--cd-motion-snap)] focus:border-[var(--cd-accent)]"
                style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)', color: 'var(--cd-text-primary)' }}
              />
            </div>
            <button
              type="button"
              onClick={onToggleFollowingOnly}
              aria-pressed={followingOnly}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-3 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
              style={{
                borderColor: followingOnly ? 'var(--cd-accent)' : 'var(--cd-border-default)',
                backgroundColor: followingOnly ? 'var(--cd-accent-muted)' : 'transparent',
                color: followingOnly ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
              }}
            >
              <Star className="size-3.5" fill={followingOnly ? 'currentColor' : 'none'} aria-hidden="true" />
              Following
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-5">
          <KpiTile label="Live" value={kpis.live} />
          <KpiTile label="Today" value={kpis.today} />
          <KpiTile label="This week" value={kpis.thisWeek} />
          <KpiTile label="AI markets" value={kpis.aiMarkets} />
          <KpiTile label="Competitions" value={kpis.competitions} />
        </div>
      </div>
    </CDPanel>
  )
}

function KpiTile({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-[var(--cd-radius-md)] border px-3 py-2.5 text-center" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}>
      <CDTelemetryValue value={value ?? '–'} size="sm" />
      <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
    </div>
  )
}
