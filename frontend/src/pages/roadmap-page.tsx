import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, TimelineStep } from '@/components/marketing/marketing-primitives'

const ROADMAP = [
  { status: 'shipped' as const, title: 'Four Sport Intelligence Centers', description: 'Football, Basketball, Baseball, and Table Tennis, each with matches, teams, players, and competitions.' },
  { status: 'shipped' as const, title: 'News Intelligence & Learning Intelligence', description: 'Explainable news impact scoring and a visible model-retraining pipeline.' },
  { status: 'shipped' as const, title: 'Trust & compliance ecosystem', description: 'Full legal, privacy, and security documentation, plus a public Trust Center.', },
  { status: 'in-progress' as const, title: 'Google AdSense integration', description: 'Enabling AdSense on public pages once policy and consent infrastructure are fully verified.', eta: 'Q4 2026' },
  { status: 'in-progress' as const, title: 'Public API general availability', description: 'Opening self-serve API key generation and usage dashboards beyond the current Enterprise pilot.', eta: 'Q4 2026' },
  { status: 'planned' as const, title: 'TitanIQ mobile app (iOS & Android)', description: 'A native mobile experience with push notifications for confidence shifts and live match intelligence — with Google AdMob integration for the free tier.', eta: '2027' },
  { status: 'planned' as const, title: 'Additional sports coverage', description: 'Expanding beyond the current four sports based on data quality and community demand.', eta: '2027' },
  { status: 'planned' as const, title: 'Team & organization accounts', description: 'Shared workspaces for media and analyst teams collaborating on TitanIQ intelligence.', eta: '2027' },
]

export default function RoadmapPage() {
  return (
    <>
      <Seo
        title="Roadmap"
        description="What's shipped, what's in progress, and what's planned for TitanIQ."
        path="/roadmap"
      />
      <PageHero
        eyebrow="Roadmap"
        title="Where TitanIQ is headed."
        description="A living view of what we've shipped, what we're building now, and what's next. Timelines are estimates, not commitments."
      />

      <Section>
        <SectionHeading eyebrow="Status" title="Shipped, in progress, and planned" />
        <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
          {ROADMAP.map((item) => (
            <TimelineStep key={item.title} {...item} />
          ))}
        </div>
      </Section>
    </>
  )
}
