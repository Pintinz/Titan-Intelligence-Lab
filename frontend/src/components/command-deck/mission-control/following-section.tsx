import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { CircleDot, Shield, Trophy, Bookmark } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus } from '@/lib/sports-status'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import { CD_DOMAIN_COLOR_VAR, sportDomainFor } from '../primitives/domain'
import type { FixtureSummaryDto, TeamSummaryDto, CompetitionSummaryDto } from '@/lib/api/types'

const TYPE_META = {
  fixture: { label: 'Match', icon: CircleDot },
  team: { label: 'Team', icon: Shield },
  competition: { label: 'Competition', icon: Trophy },
} as const

/**
 * Following — real follows across every entity type `useWatchlist` supports (fixture/team/
 * competition/prediction). Every other Command Deck consumer of the watchlist today only ever
 * displays fixture follows; this is the first surface to show team and competition follows too,
 * even though nothing new was added to the backend. "Recent Updates"/"Recent AI Reports" from the
 * brief have no real event stream backing them (a follow row has no update history) — left out
 * rather than fabricated.
 */
export function FollowingSection() {
  const watchlist = useWatchlist()
  const entries = (watchlist.data ?? [])
    .filter((e) => e.entity_type === 'fixture' || e.entity_type === 'team' || e.entity_type === 'competition')
    .slice()
    .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime())
    .slice(0, 6)

  const detailQueries = useQueries({
    queries: entries.map((entry) => ({
      queryKey: ['watchlist-detail', entry.entity_type, entry.entity_ref],
      queryFn: () => {
        if (entry.entity_type === 'fixture') return sportsApi.getFixture(entry.entity_ref)
        if (entry.entity_type === 'team') return sportsApi.getTeam(entry.entity_ref)
        return sportsApi.getCompetition(entry.entity_ref)
      },
    })),
  })

  const isLoading = watchlist.isPending || (entries.length > 0 && detailQueries.some((q) => q.isPending))

  return (
    <MissionSection
      id="following"
      title="Following"
      subtitle="Matches, teams and competitions you're tracking"
      icon={<Bookmark className="size-4" aria-hidden="true" />}
      viewAllHref={entries.length > 0 ? '/app/watchlist' : undefined}
    >
      {isLoading && <MissionSkeletonGrid />}
      {!isLoading && entries.length === 0 && (
        <MissionEmptyState
          icon={Bookmark}
          title="Nothing followed yet."
          description="Start following matches, teams and competitions to build your personal intelligence feed."
        />
      )}
      {!isLoading && entries.length > 0 && (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry, i) => {
            const detail = detailQueries[i]?.data
            if (!detail) return null
            if (entry.entity_type === 'fixture') return <FollowedFixtureTile key={entry.id} fixture={detail as FixtureSummaryDto} />
            if (entry.entity_type === 'team') return <FollowedTeamTile key={entry.id} team={detail as TeamSummaryDto} />
            return <FollowedCompetitionTile key={entry.id} competition={detail as CompetitionSummaryDto} />
          })}
        </div>
      )}
    </MissionSection>
  )
}

function TileShell({ kind, sportSlug, href, children }: { kind: keyof typeof TYPE_META; sportSlug: string; href: string; children: ReactNode }) {
  const { label, icon: Icon } = TYPE_META[kind]
  const domain = sportDomainFor(sportSlug)
  const iconColor = domain ? CD_DOMAIN_COLOR_VAR[domain] : 'var(--cd-accent)'
  return (
    <Link
      to={href}
      className="group overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="mb-2 flex items-center gap-1.5">
        <Icon className="size-3 shrink-0" style={{ color: iconColor }} aria-hidden="true" />
        <span className="font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {label}
        </span>
      </div>
      {children}
    </Link>
  )
}

function FollowedFixtureTile({ fixture }: { fixture: FixtureSummaryDto }) {
  const sportSlug = (fixture.sport_code ?? 'football').replace('_', '-')
  const status = fixtureCardStatus(fixture.status)
  return (
    <TileShell kind="fixture" sportSlug={sportSlug} href={`/app/${sportSlug}/matches/${fixture.id}`}>
      <p className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {fixture.home_team?.name ?? 'TBD'} vs {fixture.away_team?.name ?? 'TBD'}
      </p>
      <p className="mt-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
        {status === 'live' ? 'Live now' : new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
      </p>
    </TileShell>
  )
}

function FollowedTeamTile({ team }: { team: TeamSummaryDto }) {
  const sportSlug = team.sport_code.replace('_', '-')
  return (
    <TileShell kind="team" sportSlug={sportSlug} href={`/app/${sportSlug}/teams/${team.id}`}>
      <div className="flex items-center gap-2.5">
        {team.logo_url ? (
          <img src={team.logo_url} alt="" className="size-6 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[11px] font-semibold" style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}>
            {team.name.charAt(0).toUpperCase()}
          </span>
        )}
        <p className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          {team.name}
        </p>
      </div>
    </TileShell>
  )
}

function FollowedCompetitionTile({ competition }: { competition: CompetitionSummaryDto }) {
  const sportSlug = competition.sport_code.replace('_', '-')
  return (
    <TileShell kind="competition" sportSlug={sportSlug} href={`/app/${sportSlug}/competitions/${competition.id}`}>
      <div className="flex items-center gap-2.5">
        {competition.logo_url ? (
          <img src={competition.logo_url} alt="" className="size-6 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[11px] font-semibold" style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}>
            {competition.name.charAt(0).toUpperCase()}
          </span>
        )}
        <p className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          {competition.name}
        </p>
      </div>
    </TileShell>
  )
}
