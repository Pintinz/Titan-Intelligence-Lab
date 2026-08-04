import { Briefcase, Globe2, Heart, Rocket, Scale, Users } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading, Hairline } from '@/pages/landing/section-primitives'
import { PageHero, ValueCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const VALUES = [
  { icon: Scale, title: 'Calibration over confidence theater', description: 'We\'d rather ship an honest 60% than a persuasive 95% that isn\'t earned.' },
  { icon: Users, title: 'Small team, real ownership', description: 'Every engineer here owns a Sport Intelligence Center or a platform layer end to end.' },
  { icon: Globe2, title: 'Distributed-first', description: 'We hire across time zones and optimize for async, written communication over meetings.' },
  { icon: Heart, title: 'Sport, taken seriously', description: 'The team is made of people who actually watch the matches the models predict.' },
]

const OPEN_ROLES = [
  { title: 'Senior Backend Engineer — Prediction Pipeline', team: 'Engineering', location: 'Remote' },
  { title: 'Frontend Engineer — Intelligence Surfaces', team: 'Engineering', location: 'Remote' },
  { title: 'Machine Learning Engineer — Confidence Calibration', team: 'Data Science', location: 'Remote' },
  { title: 'Data Partnerships Lead', team: 'Business', location: 'Remote' },
  { title: 'Developer Relations Engineer', team: 'Developer Platform', location: 'Remote' },
]

export default function CareersPage() {
  return (
    <>
      <Seo
        title="Careers"
        description="Join Titan Intelligence Labs and help build explainable sports intelligence. Open roles in engineering, data science, and developer relations."
        path="/careers"
      />
      <PageHero
        eyebrow="Careers"
        title="Build the intelligence layer sport deserves."
        description="Titan Intelligence Labs is a small, distributed team building TitanIQ. We're looking for people who care as much about being right for the right reasons as being right."
        actions={
          <Button asChild size="lg">
            <a href="mailto:careers@titaniq.ai">Email careers@titaniq.ai</a>
          </Button>
        }
      />

      <Section>
        <SectionHeading eyebrow="How we work" title="What it's like here" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {VALUES.map((v) => (
            <ValueCard key={v.title} {...v} />
          ))}
        </div>
      </Section>

      <Hairline />

      <Section>
        <SectionHeading eyebrow="Open roles" title="Current openings" description="Don't see a fit? Email us anyway — we're always interested in exceptional people." />
        <div className="divide-y divide-border-subtle rounded-lg border border-border-default bg-bg-elevated">
          {OPEN_ROLES.map((role) => (
            <div key={role.title} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <Briefcase className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
                <div>
                  <p className="font-display text-sm font-semibold text-text-primary">{role.title}</p>
                  <p className="mt-0.5 text-xs text-text-muted">{role.team} · {role.location}</p>
                </div>
              </div>
              <Button asChild variant="secondary" size="sm" className="self-start sm:self-auto">
                <a href={`mailto:careers@titaniq.ai?subject=${encodeURIComponent('Application: ' + role.title)}`}>Apply</a>
              </Button>
            </div>
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle text-center">
        <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-accent-primary-muted">
          <Rocket className="size-5 text-accent-primary" aria-hidden="true" />
        </div>
        <h2 className="mt-4 font-display text-xl font-semibold text-text-primary">Don't see your role?</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">
          We're a small team and hire opportunistically for strong generalists. Send us what you're great at.
        </p>
        <Button asChild variant="secondary" className="mt-6">
          <a href="mailto:careers@titaniq.ai">careers@titaniq.ai</a>
        </Button>
      </Section>
    </>
  )
}
