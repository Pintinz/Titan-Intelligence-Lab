import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'

const SECTIONS = [
  { id: 'live-intelligence', label: 'Live' },
  { id: 'predictions', label: 'Predictions' },
  { id: 'featured-match', label: 'Match' },
  { id: 'sports-explorer', label: 'Sports' },
  { id: 'knowledge-graph', label: 'Graph' },
  { id: 'news', label: 'News' },
  { id: 'model-intelligence', label: 'Models' },
  { id: 'how-it-works', label: 'How it works' },
  { id: 'pricing', label: 'Pricing' },
  { id: 'faq', label: 'FAQ' },
]

/** Sticky in-page section-jump nav, scoped to the landing page only (not the shared
 * marketing-shell header, which is used across pages that don't have these anchors). Active
 * section is tracked via IntersectionObserver rather than scroll-position math. */
export function LandingNav() {
  const [active, setActive] = useState(SECTIONS[0].id)

  useEffect(() => {
    const elements = SECTIONS.map((s) => document.getElementById(s.id)).filter((el): el is HTMLElement => Boolean(el))
    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.id)
      },
      { rootMargin: '-15% 0px -70% 0px' },
    )
    elements.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  return (
    <nav
      aria-label="Page sections"
      className="sticky top-16 z-30 -mx-6 overflow-x-auto border-b border-border-subtle bg-bg-primary/90 px-6 py-2 backdrop-blur-[var(--blur-glass-sm)] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div className="mx-auto flex max-w-6xl gap-1">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            className={cn(
              'shrink-0 whitespace-nowrap rounded-full px-3 py-1 font-mono text-xs transition-colors',
              active === section.id ? 'bg-accent-primary-muted text-accent-primary' : 'text-text-muted hover:text-text-primary',
            )}
          >
            {section.label}
          </a>
        ))}
      </div>
    </nav>
  )
}
