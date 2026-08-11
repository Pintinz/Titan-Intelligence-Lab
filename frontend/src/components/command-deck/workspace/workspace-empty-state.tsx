import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CalendarSearch, Users, Trophy, Sparkles, Waypoints, ArrowUp } from 'lucide-react'
import { CD_DOMAIN_COLOR_VAR } from '../primitives/domain'

const QUICK_LINKS = [
  { label: 'Find a Match', href: '/app/live', icon: CalendarSearch },
  { label: 'Explore Teams', href: '/app/teams', icon: Users },
  { label: 'Explore Competitions', href: '/app/competitions', icon: Trophy },
  { label: 'Open AI Picks', href: '/app/picks', icon: Sparkles },
  { label: 'Explore Knowledge Graph', href: '/app/graph', icon: Waypoints },
]

/**
 * WorkspaceEmptyState — "Start an Investigation." The illustration is a hand-drawn constellation
 * (a handful of connected nodes, the same visual grammar the Knowledge Graph panel uses for real
 * data) rather than a stock graphic or a generic icon-in-a-circle — it previews what the workspace
 * actually looks like once something is focused, instead of decorating empty space.
 *
 * The composer-styled search box here is the same `query`/`onQueryChange` state the Hero's search
 * owns — a second entry point into real search, not a decorative or inert echo of the composer.
 * `searchResults` is that same search's results/"No matches" panel, rendered right under this box
 * — the results used to only render up near the Hero's own (often scrolled-out-of-view) search
 * bar, so typing here looked like it did nothing even though a real search ran and returned real
 * (or zero) matches. Quick links are real existing routes (Live/Teams/Competitions/AI Picks/the
 * standalone Knowledge Graph explorer), never fabricated destinations.
 */
export function WorkspaceEmptyState({
  query,
  onQueryChange,
  onRestoreSession,
  hasSavedSession,
  searchResults,
}: {
  query: string
  onQueryChange: (value: string) => void
  onRestoreSession: () => void
  hasSavedSession: boolean
  searchResults?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-6 rounded-[var(--cd-radius-2xl)] border px-6 py-14 text-center" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
      <svg width="180" height="120" viewBox="0 0 180 120" aria-hidden="true">
        <g stroke="var(--cd-border-strong)" strokeWidth={1} opacity={0.7}>
          <line x1="90" y1="60" x2="40" y2="28" />
          <line x1="90" y1="60" x2="140" y2="30" />
          <line x1="90" y1="60" x2="34" y2="92" />
          <line x1="90" y1="60" x2="150" y2="86" />
          <line x1="90" y1="60" x2="90" y2="14" />
          <line x1="40" y1="28" x2="90" y2="14" />
          <line x1="140" y1="30" x2="90" y2="14" />
        </g>
        <circle cx="90" cy="60" r="7" fill={CD_DOMAIN_COLOR_VAR['knowledge-graph']} />
        {[
          [40, 28],
          [140, 30],
          [34, 92],
          [150, 86],
          [90, 14],
        ].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r={4} fill="var(--cd-surface-3)" stroke="var(--cd-border-strong)" strokeWidth={1} />
        ))}
      </svg>

      <div className="max-w-md">
        <h2 className="font-[var(--cd-font-display)] text-[19px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Start an Investigation
        </h2>
        <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
          Search any match, team, competition, or player — or open a fixture from anywhere in TitanIQ. The workspace will assemble every connected prediction, evidence panel, and Knowledge Graph relationship automatically.
        </p>
      </div>

      <div className="w-full max-w-md rounded-[var(--cd-radius-lg)] border p-2" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)' }}>
        <div className="flex items-center gap-2 px-1.5">
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Ask TitanIQ to investigate something…"
            className="h-9 flex-1 bg-transparent font-[var(--cd-font-body)] text-[13px] outline-none placeholder:text-[var(--cd-text-muted)]"
            style={{ color: 'var(--cd-text-primary)' }}
          />
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}>
            <ArrowUp className="size-3" aria-hidden="true" />
          </span>
        </div>
      </div>

      {searchResults && <div className="w-full max-w-md text-left">{searchResults}</div>}

      <div className="flex flex-wrap items-center justify-center gap-2">
        {QUICK_LINKS.map((link) => (
          <Link
            key={link.href}
            to={link.href}
            className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-snap)]"
            style={{ borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-secondary)' }}
          >
            <link.icon className="size-3.5" aria-hidden="true" />
            {link.label}
          </Link>
        ))}
      </div>

      {hasSavedSession && (
        <button
          type="button"
          onClick={onRestoreSession}
          className="rounded-[var(--cd-radius-md)] border px-3.5 py-2 font-[var(--cd-font-body)] text-[12px] font-medium"
          style={{ borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-secondary)' }}
        >
          Restore your last saved session
        </button>
      )}
    </div>
  )
}
