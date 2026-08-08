import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronDown } from 'lucide-react'
import { CD_DOMAIN_COLOR_VAR, type DomainKey } from './primitives/domain'
import type { TeamSummaryDto } from '@/lib/api/types'

const ROW_HEIGHT = 44

type Row = { kind: 'header'; letter: string; count: number } | { kind: 'team'; team: TeamSummaryDto }

/**
 * TeamBrowseList — "Browse All Teams": alphabetically grouped, collapsible, and virtualized via
 * `@tanstack/react-virtual` so football's real 87 rows (and however many a production sport grows
 * to) never render more DOM than the viewport needs. Deliberately lean rows — crest thumbnail,
 * name, country text only, no per-row league/AI-ready/Generate-Intelligence derivation — this
 * section is for fast scan-and-jump across the full roster, not per-team evaluation; that lives in
 * Discover Teams above. Groups default expanded (this is a browse surface, not a picker — hiding
 * every row behind a click would fight "encourage exploration") but each stays collapsible.
 */
export function TeamBrowseList({
  teams,
  sportSlug,
  sportDomain,
}: {
  teams: TeamSummaryDto[]
  sportSlug: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)

  const groups = useMemo(() => {
    const byLetter = new Map<string, TeamSummaryDto[]>()
    for (const team of [...teams].sort((a, b) => a.name.localeCompare(b.name))) {
      const letter = /[A-Za-z]/.test(team.name[0]) ? team.name[0].toUpperCase() : '#'
      if (!byLetter.has(letter)) byLetter.set(letter, [])
      byLetter.get(letter)!.push(team)
    }
    return [...byLetter.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [teams])

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = []
    for (const [letter, group] of groups) {
      out.push({ kind: 'header', letter, count: group.length })
      if (!collapsed.has(letter)) {
        for (const team of group) out.push({ kind: 'team', team })
      }
    }
    return out
  }, [groups, collapsed])

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  })

  function toggle(letter: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(letter)) next.delete(letter)
      else next.add(letter)
      return next
    })
  }

  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]

  return (
    <div
      ref={scrollRef}
      className="max-h-[640px] overflow-y-auto rounded-[var(--cd-radius-xl)] border"
      style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index]
          return (
            <div
              key={virtualRow.key}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: virtualRow.size, transform: `translateY(${virtualRow.start}px)` }}
            >
              {row.kind === 'header' ? (
                <button
                  type="button"
                  onClick={() => toggle(row.letter)}
                  aria-expanded={!collapsed.has(row.letter)}
                  className="flex h-full w-full items-center justify-between gap-2 border-b px-4 text-left transition-colors duration-[var(--cd-motion-snap)]"
                  style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-[var(--cd-font-display)] text-[14px] font-bold" style={{ color: domainColor }}>
                      {row.letter}
                    </span>
                    <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                      {row.count}
                    </span>
                  </span>
                  <ChevronDown
                    className="size-3.5 shrink-0 transition-transform duration-[var(--cd-motion-base)]"
                    style={{ color: 'var(--cd-text-muted)', transform: collapsed.has(row.letter) ? 'rotate(-90deg)' : 'none' }}
                    aria-hidden="true"
                  />
                </button>
              ) : (
                <Link
                  to={`/app/${sportSlug}/teams/${row.team.id}`}
                  className="flex h-full w-full items-center gap-3 border-b px-4 transition-colors duration-[var(--cd-motion-snap)] hover:bg-[var(--cd-surface-2)]"
                  style={{ borderColor: 'var(--cd-border-hairline)' }}
                >
                  {row.team.logo_url ? (
                    <img src={row.team.logo_url} alt="" className="size-6 shrink-0 object-contain" loading="lazy" />
                  ) : (
                    <span
                      aria-hidden="true"
                      className="flex size-6 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[10px] font-semibold"
                      style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
                    >
                      {row.team.name.charAt(0).toUpperCase()}
                    </span>
                  )}
                  <span className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                    {row.team.name}
                  </span>
                  {row.team.country && (
                    <span className="ml-auto shrink-0 truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                      {row.team.country}
                    </span>
                  )}
                </Link>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
