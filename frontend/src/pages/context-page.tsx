import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Newspaper, MessageCircle, HeartPulse, ArrowLeftRight, ArrowUpRight, Star } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useContextIntelligence } from '@/lib/hooks/use-context-intelligence'
import { SPORT_SLUGS, type SportMeta } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { ContextHero } from '@/components/command-deck/context-hero'
import { MissionSection, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import { CD_DOMAIN_COLOR_VAR, domainTint } from '@/components/command-deck/primitives/domain'

const ROW_CLASS =
  'group/row flex items-start gap-3 rounded-[var(--cd-radius-xl)] p-3.5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]'
const ROW_STYLE = { background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' } as const

function RowIcon({ domain, icon: Icon }: { domain: 'news' | 'community' | 'alerts'; icon: typeof Newspaper }) {
  const color = CD_DOMAIN_COLOR_VAR[domain]
  return (
    <span
      className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full transition-transform duration-[var(--cd-motion-base)] group-hover/row:scale-105"
      style={{ backgroundColor: domainTint(domain, 14), color, boxShadow: `0 0 0 1px ${domainTint(domain, 32)} inset` }}
      aria-hidden="true"
    >
      <Icon className="size-3.5" />
    </span>
  )
}

/**
 * Context — the consolidated news/injuries/transfers/community destination (information-
 * architecture restructure). Redirected here from the two orphaned per-sport News/Community
 * pages (which had no nav entry and no in-app callers). Suspensions and Lineups have no
 * consumer-facing read endpoint anywhere in the backend (confirmed via a full grep of
 * `lib/api/` — only an admin lineup sync-trigger exists) — deliberately omitted, never faked.
 * `?sport=` seeds the injuries/transfers sport scope from the old per-sport route's redirect.
 */
export default function ContextPage() {
  const [searchParams] = useSearchParams()
  const seedSlug = searchParams.get('sport')
  const seedSport = SPORT_SLUGS.find((s) => s.slug === seedSlug) ?? SPORT_SLUGS[0]

  const [sport, setSport] = useState<SportMeta>(seedSport)
  const [search, setSearch] = useState('')
  const watchlist = useWatchlist()

  const trimmed = search.trim()
  const newsQuery = useQuery({
    queryKey: ['intelligence', 'news', 'context', trimmed],
    queryFn: () => intelligenceApi.searchNews({ query: trimmed || undefined, limit: 20 }),
  })
  const communityQuery = useQuery({ queryKey: ['intelligence', 'community', 'context'], queryFn: () => intelligenceApi.communityTopics() })

  const followedTeamRefs = useMemo(
    () => (watchlist.data ?? []).filter((e) => e.entity_type === 'team').map((e) => e.entity_ref),
    [watchlist.data],
  )
  const { followedTeams, injuriesByTeam, transfersByTeam, isLoading: contextLoading, isError: contextError, error: contextErrorObj } =
    useContextIntelligence(sport.code, followedTeamRefs)

  const news = newsQuery.data ?? []
  const community = (communityQuery.data ?? []).slice().sort((a, b) => (b.momentum ?? 0) - (a.momentum ?? 0))

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <ContextHero sport={sport} onSportChange={setSport} search={search} onSearchChange={setSearch} />

      <MissionSection title="News" subtitle="Real, sourced articles — never full-text reproduction" icon={<Newspaper className="size-4" aria-hidden="true" />} domain="news">
        {newsQuery.isError && <ErrorState error={newsQuery.error} onRetry={() => void newsQuery.refetch()} />}
        {!newsQuery.isError && newsQuery.isPending && (
          <div className="space-y-2.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-[var(--cd-radius-xl)]" style={ROW_STYLE} />
            ))}
          </div>
        )}
        {!newsQuery.isError && !newsQuery.isPending && news.length === 0 && (
          <MissionEmptyState
            icon={Newspaper}
            title={trimmed ? 'No news matched your search' : 'TitanIQ is watching every synced source.'}
            description={trimmed ? `Nothing matches "${trimmed}" — try a different search.` : 'Real news will appear here as soon as something surfaces.'}
          />
        )}
        {!newsQuery.isError && !newsQuery.isPending && news.length > 0 && (
          <ul className="space-y-2.5">
            {news.map((article) => (
              <li key={article.id}>
                <a href={article.url} target="_blank" rel="noopener noreferrer">
                  <div className={ROW_CLASS} style={ROW_STYLE}>
                    <RowIcon domain="news" icon={Newspaper} />
                    <div className="min-w-0 flex-1">
                      <span className="font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                        {new Date(article.published_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </span>
                      <p className="mt-0.5 line-clamp-2 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                        {article.title}
                      </p>
                    </div>
                    <ArrowUpRight className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </MissionSection>

      {community.length > 0 && (
        <MissionSection title="Community Signal" subtitle="Topics gaining real momentum across tracked platforms" icon={<MessageCircle className="size-4" aria-hidden="true" />} domain="community">
          <ul className="space-y-2.5">
            {community.slice(0, 8).map((topic) => (
              <li key={topic.id} className={ROW_CLASS} style={ROW_STYLE}>
                <RowIcon domain="community" icon={MessageCircle} />
                <div className="min-w-0 flex-1">
                  <p className="font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                    {topic.topic_label}
                  </p>
                  <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                    {topic.platform} · {topic.post_count} posts{topic.momentum !== null ? ` · momentum ${topic.momentum.toFixed(1)}` : ''}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </MissionSection>
      )}

      <MissionSection
        title="Injuries & Transfers"
        subtitle={`For the ${sport.label} teams you follow`}
        icon={<HeartPulse className="size-4" aria-hidden="true" />}
      >
        {contextError && <ErrorState error={contextErrorObj} onRetry={() => window.location.reload()} />}
        {!contextError && contextLoading && (
          <div className="space-y-2.5">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-[var(--cd-radius-xl)]" style={ROW_STYLE} />
            ))}
          </div>
        )}
        {!contextError && !contextLoading && followedTeams.length === 0 && (
          <MissionEmptyState
            icon={Star}
            title="Follow a team to see its injury and transfer intelligence here"
            description={`Follow any ${sport.label} team from Teams or a Match page — TitanIQ has no global injury/transfer feed, only real per-team data.`}
          />
        )}
        {!contextError && !contextLoading && followedTeams.length > 0 && injuriesByTeam.length === 0 && transfersByTeam.length === 0 && (
          <MissionEmptyState icon={HeartPulse} title="No reported injuries or transfers" description="Nothing reported right now for the teams you follow." />
        )}
        {!contextError && !contextLoading && (injuriesByTeam.length > 0 || transfersByTeam.length > 0) && (
          <ul className="space-y-2.5">
            {injuriesByTeam.flatMap(({ team, injuries }) =>
              injuries.map((injury) => (
                <li key={injury.id} className={ROW_CLASS} style={ROW_STYLE}>
                  <RowIcon domain="alerts" icon={HeartPulse} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {team.logo_url && <img src={team.logo_url} alt="" className="size-3.5 shrink-0 object-contain" loading="lazy" />}
                      <span className="truncate font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                        {team.name}
                      </span>
                    </div>
                    <p className="mt-0.5 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                      {injury.player_name ?? 'Unknown player'} — {injury.status}
                    </p>
                    {injury.reason && (
                      <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                        {injury.reason}
                      </p>
                    )}
                  </div>
                </li>
              )),
            )}
            {transfersByTeam.flatMap(({ team, transfers }) =>
              transfers.map((transfer) => (
                <li key={transfer.id} className={ROW_CLASS} style={ROW_STYLE}>
                  <RowIcon domain="alerts" icon={ArrowLeftRight} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {team.logo_url && <img src={team.logo_url} alt="" className="size-3.5 shrink-0 object-contain" loading="lazy" />}
                      <span className="truncate font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                        {team.name}
                      </span>
                    </div>
                    <p className="mt-0.5 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                      {transfer.player_name ?? 'Unknown player'}
                      {transfer.from_team_name || transfer.to_team_name
                        ? ` — ${transfer.from_team_name ?? '?'} → ${transfer.to_team_name ?? '?'}`
                        : ''}
                    </p>
                    <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                      {new Date(transfer.effective_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                      {transfer.transfer_type ? ` · ${transfer.transfer_type}` : ''}
                    </p>
                  </div>
                </li>
              )),
            )}
          </ul>
        )}
      </MissionSection>
    </div>
  )
}
