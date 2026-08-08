import type { DomainKey } from '@/components/infinity/primitives/badge'

export type { DomainKey }

/** Maps a domain key to its Command Deck CSS var — the single source of truth every
 * domain-aware Command Deck component reads from. Mirrors Infinity's `DOMAIN_COLOR_VAR`
 * hue-for-hue (same `DomainKey` union, same meaning in both visual worlds) but resolves
 * through `--cd-domain-*`, this world's own token namespace. */
export const CD_DOMAIN_COLOR_VAR: Record<DomainKey, string> = {
  football: 'var(--cd-domain-football)',
  basketball: 'var(--cd-domain-basketball)',
  baseball: 'var(--cd-domain-baseball)',
  'table-tennis': 'var(--cd-domain-table-tennis)',
  predictions: 'var(--cd-domain-predictions)',
  'knowledge-graph': 'var(--cd-domain-knowledge-graph)',
  learning: 'var(--cd-domain-learning)',
  news: 'var(--cd-domain-news)',
  community: 'var(--cd-domain-community)',
  operations: 'var(--cd-domain-operations)',
  infrastructure: 'var(--cd-domain-infrastructure)',
  alerts: 'var(--cd-domain-alerts)',
  security: 'var(--cd-domain-security)',
}

/** A domain hue tinted to a low, muted opacity via `color-mix()` — the same technique already
 * used throughout tokens.command-deck.css for `--cd-accent-muted`/`--cd-card-border`/etc.,
 * applied per-domain at point of use instead of pre-baking a muted/strong variant for every
 * one of the 13 domains into the token file. */
export function domainTint(domain: DomainKey, opacityPct = 14): string {
  return `color-mix(in srgb, ${CD_DOMAIN_COLOR_VAR[domain]} ${opacityPct}%, transparent)`
}

type SportDomainKey = Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

/** Narrows a `SportMeta.slug` (plain `string`) to a sport `DomainKey` — every real sport slug
 * in `SPORT_SLUGS` matches a domain key exactly, but the two types aren't structurally linked,
 * so this is the one place that connects them for every Mission Control card. */
export function sportDomainFor(slug: string): SportDomainKey | undefined {
  return slug === 'football' || slug === 'basketball' || slug === 'baseball' || slug === 'table-tennis' ? slug : undefined
}
