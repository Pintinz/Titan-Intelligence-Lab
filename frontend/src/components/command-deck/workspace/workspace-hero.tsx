import { Search, Sparkles, GitCompare, Waypoints, History } from 'lucide-react'
import type { ReactNode } from 'react'
import type { SportMeta } from '@/lib/hooks/use-sport'
import { SportSegmentedControl } from '../primitives/sport-segmented-control'
import { domainTint } from '../primitives/domain'
import type { EntityKind } from '@/lib/hooks/use-investigation-workspace'

const ENTITY_KIND_LABELS: Record<EntityKind, string> = {
  fixture: 'Matches',
  team: 'Teams',
  competition: 'Competitions',
  player: 'Players',
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export interface QuickActionSpec {
  key: string
  label: string
  icon: ReactNode
  onClick: () => void
  disabled?: boolean
}

/**
 * WorkspaceHero — the Intelligence Workspace's opening instrument. Same stadium-glow/telemetry-
 * grid atmosphere already proven on Competition/Team Hero (knowledge-graph-tinted second blob
 * doubles as "knowledge graph particles" without inventing new imagery), plus a glass search that
 * recognizes a pasted UUID as a direct Prediction ID lookup rather than an entity search.
 */
export function WorkspaceHero({
  sport,
  onSportChange,
  entityKind,
  onEntityKindChange,
  query,
  onQueryChange,
  onPredictionIdOpen,
  quickActions,
  recentCount,
  onOpenRecent,
}: {
  sport: SportMeta
  onSportChange: (sport: SportMeta) => void
  entityKind: EntityKind
  onEntityKindChange: (kind: EntityKind) => void
  query: string
  onQueryChange: (value: string) => void
  onPredictionIdOpen: (predictionId: string) => void
  quickActions: QuickActionSpec[]
  recentCount: number
  onOpenRecent: () => void
}) {
  const isUuid = UUID_RE.test(query.trim())

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 sm:p-9"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" aria-hidden="true">
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -left-[8%] -top-[32%] h-[440px] w-[440px] rounded-full opacity-60"
          style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
        />
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -right-[8%] -top-[8%] h-[360px] w-[360px] rounded-full opacity-45"
          style={{ background: `radial-gradient(circle, ${domainTint('knowledge-graph', 24)} 0%, transparent 70%)`, animationDelay: '2.5s' }}
        />
        <div
          className="absolute inset-0 opacity-[0.045]"
          style={{
            backgroundImage:
              'linear-gradient(var(--cd-text-primary) 1px, transparent 1px), linear-gradient(90deg, var(--cd-text-primary) 1px, transparent 1px)',
            backgroundSize: '46px 46px',
            maskImage: 'radial-gradient(ellipse 85% 60% at 50% 0%, black 0%, transparent 74%)',
            WebkitMaskImage: 'radial-gradient(ellipse 85% 60% at 50% 0%, black 0%, transparent 74%)',
          }}
        />
      </div>

      <div className="relative flex flex-col gap-6">
        <div>
          <h1
            className="font-[var(--cd-font-display)] text-[26px] font-semibold uppercase leading-tight tracking-[-0.01em] sm:text-[32px]"
            style={{ color: 'var(--cd-text-primary)' }}
          >
            Intelligence Workspace
          </h1>
          <p className="mt-2.5 max-w-xl font-[var(--cd-font-body)] text-[13.5px] leading-relaxed sm:text-[15px]" style={{ color: 'var(--cd-text-secondary)' }}>
            Investigate predictions, compare teams, inspect evidence, and explore every relationship powering TitanIQ's AI.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <div className="relative w-full max-w-lg">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Search matches, teams, competitions, players, or paste a prediction ID…"
              className="h-11 w-full rounded-[var(--cd-radius-md)] border pl-10 pr-24 backdrop-blur-md font-[var(--cd-font-body)] text-[13.5px] outline-none transition-colors duration-[var(--cd-motion-snap)] focus:border-[var(--cd-accent)]"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 65%, transparent)', color: 'var(--cd-text-primary)' }}
            />
            {isUuid && (
              <button
                type="button"
                onClick={() => onPredictionIdOpen(query.trim())}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-[var(--cd-radius-sm)] px-2.5 py-1.5 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.05em]"
                style={{ backgroundColor: 'var(--cd-accent)', color: 'var(--cd-text-inverse)' }}
              >
                Open
              </button>
            )}
          </div>

          {!isUuid && (
            <div className="flex flex-wrap items-center gap-3">
              <SportSegmentedControl sport={sport} onSportChange={onSportChange} />
              <div className="flex w-fit gap-1 overflow-x-auto rounded-[var(--cd-radius-md)] border p-1" style={{ borderColor: 'var(--cd-border-default)' }}>
                {(Object.keys(ENTITY_KIND_LABELS) as EntityKind[]).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => onEntityKindChange(kind)}
                    className="shrink-0 rounded-[var(--cd-radius-sm)] px-2.5 py-1 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-snap)]"
                    style={{
                      backgroundColor: entityKind === kind ? 'var(--cd-accent-muted)' : 'transparent',
                      color: entityKind === kind ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
                    }}
                  >
                    {ENTITY_KIND_LABELS[kind]}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {quickActions.map((action) => (
            <button
              key={action.key}
              type="button"
              onClick={action.onClick}
              disabled={action.disabled}
              className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-snap)] disabled:cursor-not-allowed disabled:opacity-40"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 55%, transparent)', color: 'var(--cd-text-secondary)' }}
            >
              {action.icon}
              {action.label}
            </button>
          ))}
          {recentCount > 0 && (
            <button
              type="button"
              onClick={onOpenRecent}
              className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium"
              style={{ color: 'var(--cd-text-muted)' }}
            >
              <History className="size-3.5" aria-hidden="true" />
              Recent investigations ({recentCount})
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export const WORKSPACE_QUICK_ACTION_ICONS = {
  generate: <Sparkles className="size-3.5" aria-hidden="true" />,
  compare: <GitCompare className="size-3.5" aria-hidden="true" />,
  graph: <Waypoints className="size-3.5" aria-hidden="true" />,
}
