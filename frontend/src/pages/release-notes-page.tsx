import { Seo } from '@/components/seo/seo'
import { Section } from '@/pages/landing/section-primitives'
import { PageHero } from '@/components/marketing/marketing-primitives'
import { cn } from '@/lib/cn'

const RELEASES = [
  {
    version: 'v10.3.0',
    date: 'July 29, 2026',
    tag: 'Milestone 10.3',
    title: 'Premium authentication experience & trust ecosystem',
    changes: [
      'Redesigned login, signup, forgot-password, and reset-password into a split-screen Intelligence Canvas experience.',
      'Added form morphing between login and signup with directional motion — no page navigation required.',
      'Published the complete legal, compliance, and trust ecosystem: Privacy, Terms, Cookie, Advertising, Editorial, Responsible AI, Security, Copyright, DMCA, Acceptable Use, Disclaimer, Licenses, GDPR, and CCPA policies, plus a Trust Center.',
      'Rebuilt global navigation with a full mega-menu header and enterprise footer.',
    ],
  },
  {
    version: 'v10.2.5',
    date: 'July 2026',
    tag: 'Milestone 10.2 · Phase 5',
    title: 'TitanIQ Insights',
    changes: ['Launched the cross-sport Insights surface, aggregating trends and analytics across all four Sport Intelligence Centers.'],
  },
  {
    version: 'v10.2.4',
    date: 'June 2026',
    tag: 'Milestone 10.2 · Phase 4',
    title: 'News Intelligence & Learning Intelligence',
    changes: [
      'Shipped News Intelligence — headline, TitanIQ summary, prediction impact, and confidence impact for every relevant story.',
      'Shipped Learning Intelligence, visualizing the prediction → validation → evaluation → recalibration → retraining loop.',
    ],
  },
  {
    version: 'v10.2.3',
    date: 'June 2026',
    tag: 'Milestone 10.2 · Phase 3',
    title: 'Basketball, Baseball & Table Tennis Intelligence Centers',
    changes: ['Extended the Sport Intelligence Center template — proven on Football — to Basketball, Baseball, and Table Tennis.'],
  },
  {
    version: 'v10.2.2',
    date: 'May 2026',
    tag: 'Milestone 10.2 · Phase 2',
    title: 'Football Intelligence Center',
    changes: ['Shipped the first complete Sport Intelligence Center template: matches, teams, players, competitions, and the Prediction Lab.'],
  },
  {
    version: 'v10.2.1',
    date: 'May 2026',
    tag: 'Milestone 10.2 · Phase 1',
    title: 'Landing page rebuild',
    changes: ['Rebuilt the public landing page around live Intelligence Canvas storytelling instead of a static marketing hero.'],
  },
]

export default function ReleaseNotesPage() {
  return (
    <>
      <Seo
        title="Release Notes"
        description="What's new in TitanIQ — a changelog of shipped features and improvements."
        path="/release-notes"
      />
      <PageHero
        eyebrow="Changelog"
        title="Release Notes"
        description="What's shipped, milestone by milestone."
      />

      <Section className="max-w-3xl">
        <div className="space-y-10">
          {RELEASES.map((release, i) => (
            <div key={release.version} className="relative pl-8">
              <span
                className={cn(
                  'absolute left-0 top-1.5 size-2.5 rounded-full',
                  i === 0 ? 'bg-accent-primary' : 'bg-border-strong',
                )}
                aria-hidden="true"
              />
              {i < RELEASES.length - 1 && (
                <span className="absolute left-[4.5px] top-4 h-full w-px bg-border-subtle" aria-hidden="true" />
              )}
              <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                <span className="font-mono font-semibold text-text-primary">{release.version}</span>
                <span aria-hidden="true">·</span>
                <time>{release.date}</time>
                <span aria-hidden="true">·</span>
                <span className="text-accent-primary">{release.tag}</span>
              </div>
              <h2 className="mt-1.5 font-display text-lg font-semibold text-text-primary">{release.title}</h2>
              <ul className="mt-2 space-y-1.5">
                {release.changes.map((change, ci) => (
                  <li key={ci} className="flex items-start gap-2 text-sm text-text-secondary">
                    <span className="mt-1.5 size-1 shrink-0 rounded-full bg-text-muted" aria-hidden="true" />
                    {change}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>
    </>
  )
}
