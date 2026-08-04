import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface TocEntry {
  id: string
  label: string
}

interface LegalPageLayoutProps {
  eyebrow: string
  title: string
  summary: string
  lastUpdated: string
  effectiveDate?: string
  toc: TocEntry[]
  children: ReactNode
}

/**
 * Shared shell for every legal/compliance document (Privacy, Terms, Cookie Policy, etc.) — hero
 * band with revision metadata plus a sticky in-page table of contents on desktop. Keeping this
 * consistent across all 15 legal pages is what makes the set read as one governed corpus rather
 * than 15 one-off pages.
 */
export function LegalPageLayout({ eyebrow, title, summary, lastUpdated, effectiveDate, toc, children }: LegalPageLayoutProps) {
  return (
    <div className="bg-bg-primary">
      <div className="border-b border-border-subtle bg-bg-secondary/30">
        <div className="mx-auto max-w-6xl px-6 py-14 lg:px-10 lg:py-20">
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            {eyebrow}
          </p>
          <h1 className="mt-2 max-w-3xl font-display text-3xl font-semibold tracking-tight text-text-primary lg:text-4xl">
            {title}
          </h1>
          <p className="mt-4 max-w-2xl text-base text-text-secondary">{summary}</p>
          <dl className="mt-6 flex flex-wrap gap-x-8 gap-y-2 text-xs text-text-muted">
            <div className="flex items-center gap-1.5">
              <dt className="font-medium">Last updated:</dt>
              <dd className="font-mono">{lastUpdated}</dd>
            </div>
            {effectiveDate && (
              <div className="flex items-center gap-1.5">
                <dt className="font-medium">Effective:</dt>
                <dd className="font-mono">{effectiveDate}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-12 lg:px-10 lg:py-16">
        <div className="lg:grid lg:grid-cols-[220px_1fr] lg:gap-12">
          <nav aria-label="Table of contents" className="hidden lg:block">
            <div className="sticky top-24 space-y-1">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-text-muted">On this page</p>
              <ul className="space-y-1 border-l border-border-subtle">
                {toc.map((entry) => (
                  <li key={entry.id}>
                    <a
                      href={`#${entry.id}`}
                      className="block -ml-px border-l border-transparent py-1 pl-4 text-sm text-text-secondary transition-colors hover:border-accent-primary hover:text-text-primary"
                    >
                      {entry.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </nav>

          <div className="min-w-0 max-w-3xl space-y-10">{children}</div>
        </div>
      </div>
    </div>
  )
}

export function LegalSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="font-display text-xl font-semibold text-text-primary">{title}</h2>
      <div className="prose-legal mt-3 space-y-3">{children}</div>
    </section>
  )
}

export function LegalParagraph({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-sm leading-relaxed text-text-secondary', className)}>{children}</p>
}

export function LegalList({ items, ordered = false }: { items: ReactNode[]; ordered?: boolean }) {
  const Tag = ordered ? 'ol' : 'ul'
  return (
    <Tag className={cn('space-y-1.5 pl-5 text-sm leading-relaxed text-text-secondary', ordered ? 'list-decimal' : 'list-disc')}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </Tag>
  )
}

export function LegalCallout({ tone = 'info', children }: { tone?: 'info' | 'warning'; children: ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-lg border px-4 py-3 text-sm leading-relaxed',
        tone === 'info' && 'border-info/30 bg-info-muted text-text-secondary',
        tone === 'warning' && 'border-warning/30 bg-warning-muted text-text-secondary',
      )}
    >
      {children}
    </div>
  )
}

export function LegalContactRow({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border-subtle py-2.5 text-sm last:border-0">
      <span className="text-text-muted">{label}</span>
      {href ? (
        <a href={href} className="font-medium text-accent-primary hover:text-accent-primary-hover">
          {value}
        </a>
      ) : (
        <span className="font-medium text-text-primary">{value}</span>
      )}
    </div>
  )
}
