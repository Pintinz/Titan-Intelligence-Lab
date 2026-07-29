import type { ReactNode } from 'react'

/** Shared prose container for the text-heavy public pages (methodology/docs/api-reference/about/
 * contact) — consistent max-width and typography, not a full design system in itself. */
export function MarketingArticle({ eyebrow, title, lede, children }: { eyebrow: string; title: string; lede?: string; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-3xl px-6 py-16">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">{eyebrow}</p>
      <h1 className="mt-2 font-display text-3xl font-semibold text-text-primary sm:text-4xl">{title}</h1>
      {lede && <p className="mt-4 text-lg text-text-secondary">{lede}</p>}
      <div className="prose-titaniq mt-10 flex flex-col gap-8">{children}</div>
    </article>
  )
}

export function ArticleSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-xl font-semibold text-text-primary">{title}</h2>
      <div className="mt-3 flex flex-col gap-3 text-sm leading-relaxed text-text-secondary">{children}</div>
    </section>
  )
}
