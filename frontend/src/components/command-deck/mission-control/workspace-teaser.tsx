import { Link } from 'react-router-dom'
import { LayoutGrid, Sparkles, GitCompare, Waypoints, FileSearch } from 'lucide-react'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { CDButton } from '../primitives/button'
import { domainTint } from '../primitives/domain'
import type { FixtureCardItem } from './live-intelligence'

/**
 * TitanIQ Workspace teaser — a premium AI workstation entry point, never a ChatGPT-style input.
 * Suggestion chips are built from real data fetched on this page each visit (not hardcoded
 * example copy): the earliest real AI-ready fixture, the two most recently followed teams (for a
 * genuine "Compare" deep-link — the Insights page pre-pins both via URL params), otherwise static
 * links to already-real destinations. A chip that has nothing real to point to is simply omitted
 * rather than shown broken.
 */
export function WorkspaceTeaser({ aiReadyFixtures }: { aiReadyFixtures: FixtureCardItem[] }) {
  const watchlist = useWatchlist()
  const earliestFixture = aiReadyFixtures[0]
  const followedTeams = (watchlist.data ?? []).filter((e) => e.entity_type === 'team')

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 backdrop-blur-md"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div
        className="pointer-events-none absolute -bottom-16 -left-16 h-56 w-56 rounded-full opacity-50"
        style={{ background: `radial-gradient(circle, ${domainTint('knowledge-graph', 22)} 0%, transparent 70%)` }}
        aria-hidden="true"
      />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-[var(--cd-font-display)] text-[17px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            TitanIQ Workspace
          </h3>
          <p className="mt-1 max-w-md font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            Pin a team or match, compare predictions, or explore Knowledge Graph connections — grounded and deterministic, every answer traces to real TitanIQ data.
          </p>
        </div>
        <CDButton variant="primary" size="md" href="/app/insights" icon={<LayoutGrid className="size-3.5" aria-hidden="true" />}>
          Open Workspace
        </CDButton>
      </div>

      <div className="relative mt-4 flex flex-wrap gap-2">
        {earliestFixture && (
          <SuggestionChip
            icon={Sparkles}
            label={`Predict ${earliestFixture.fixture.home_team?.name ?? 'TBD'} vs ${earliestFixture.fixture.away_team?.name ?? 'TBD'}`}
            href={`/app/${earliestFixture.sport.slug}/matches/${earliestFixture.fixture.id}`}
          />
        )}
        <SuggestionChip icon={Sparkles} label="Today's strongest AI picks" href="/app/picks" />
        {followedTeams.length >= 2 && (
          <SuggestionChip
            icon={GitCompare}
            label="Compare your followed teams"
            href={`/app/insights?pin_type=team&pin_id=${followedTeams[0].entity_ref}&pin_id_2=${followedTeams[1].entity_ref}`}
          />
        )}
        <SuggestionChip icon={Waypoints} label="Open Knowledge Graph" href="/app/graph" />
        <SuggestionChip icon={FileSearch} label="Review prediction evidence" href="/app/insights" />
      </div>
    </div>
  )
}

function SuggestionChip({ icon: Icon, label, href }: { icon: typeof Sparkles; label: string; href: string }) {
  return (
    <Link
      to={href}
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:border-[var(--cd-accent)] hover:text-[var(--cd-accent)] hover:shadow-[var(--cd-glow-accent)]"
      style={{ border: '1px solid var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 60%, transparent)', color: 'var(--cd-text-secondary)' }}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </Link>
  )
}
