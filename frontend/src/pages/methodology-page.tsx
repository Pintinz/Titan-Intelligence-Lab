import { Link } from 'react-router-dom'
import { Database, Cpu, Gauge, RefreshCw } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading, Hairline } from '@/pages/landing/section-primitives'
import { PageHero, ValueCard, TimelineStep } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const PIPELINE = [
  { icon: Database, title: 'Structured data', description: 'Historical results, live match events, team & player statistics, and verified news signal feed the pipeline continuously.' },
  { icon: Cpu, title: 'Modeling', description: 'Sport-specific statistical and machine-learning models produce a probability distribution over outcomes for each market.' },
  { icon: Gauge, title: 'Confidence scoring', description: 'Confidence reflects evidence strength and the model\'s historical reliability in similar situations — not how "good" an outcome is.' },
  { icon: RefreshCw, title: 'Continuous evaluation', description: 'Every completed match is scored against its prediction, feeding recalibration and retraining — see Learning Intelligence.' },
]

const LEARNING_STEPS = [
  { status: 'shipped' as const, title: 'Prediction', description: 'A model generates a probability distribution for a market ahead of or during a match.' },
  { status: 'shipped' as const, title: 'Validation', description: 'The prediction is checked against data quality and consistency rules before publication.' },
  { status: 'shipped' as const, title: 'Evaluation', description: 'Once the match concludes, the actual outcome is compared against the prediction and confidence.' },
  { status: 'shipped' as const, title: 'Knowledge Graph update', description: 'New verified facts (results, standout performances, injuries) update the underlying graph.' },
  { status: 'shipped' as const, title: 'Confidence recalibration', description: 'Confidence scoring is adjusted where evaluation reveals systematic over- or under-confidence.' },
  { status: 'shipped' as const, title: 'Retraining', description: 'Models are retrained on the expanded evaluation dataset on a recurring cycle.' },
  { status: 'shipped' as const, title: 'Improved predictions', description: 'The next prediction for a similar situation benefits from everything learned in this cycle.' },
]

export default function MethodologyPage() {
  return (
    <>
      <Seo
        title="Methodology"
        description="How TitanIQ generates predictions — data sources, modeling, confidence scoring, and the continuous learning loop."
        path="/methodology"
      />
      <PageHero
        eyebrow="Methodology"
        title="How TitanIQ actually works."
        description="No black box. Here's the pipeline that turns data into a prediction, and the loop that keeps it honest over time."
        actions={
          <Button asChild size="lg">
            <Link to="/responsible-ai">Read our Responsible AI Policy</Link>
          </Button>
        }
      />

      <Section>
        <SectionHeading eyebrow="Pipeline" title="From data to prediction" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PIPELINE.map((step) => (
            <ValueCard key={step.title} {...step} />
          ))}
        </div>
      </Section>

      <Hairline />

      <Section>
        <SectionHeading
          eyebrow="Learning Intelligence"
          title="The loop that keeps confidence honest"
          description="Predictions aren't produced once and forgotten — every outcome feeds back into the model."
        />
        <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
          {LEARNING_STEPS.map((step) => (
            <TimelineStep key={step.title} {...step} />
          ))}
        </div>
        <p className="mt-4 text-sm text-text-secondary">
          See this pipeline live in <Link to="/app/learning" className="text-accent-primary hover:text-accent-primary-hover">Learning Intelligence</Link> once
          signed in.
        </p>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Reading a score" title="What confidence does — and doesn't — mean" />
        <div className="max-w-2xl space-y-3 text-sm leading-relaxed text-text-secondary">
          <p>
            <strong className="text-text-primary">A high confidence score means the evidence is strong and consistent</strong> — not
            that the outcome is certain. Sport has genuine randomness that no model removes.
          </p>
          <p>
            <strong className="text-text-primary">A low confidence score is not a worse prediction</strong> — it's an honest signal
            that the situation is more volatile or the evidence is thinner than usual. We'd rather show you that
            than hide it behind false precision.
          </p>
          <p>
            Every prediction on TitanIQ is paired with the evidence behind it — form, news, and community signal —
            so you can judge the reasoning yourself, not just the number.
          </p>
        </div>
      </Section>

      <Section className="border-t border-border-subtle text-center">
        <h2 className="font-display text-xl font-semibold text-text-primary">Want the full policy detail?</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">
          Our <Link to="/responsible-ai" className="text-accent-primary hover:text-accent-primary-hover">Responsible AI Policy</Link> covers explainability,
          human oversight, bias monitoring, and the limits of what any model can honestly claim.
        </p>
      </Section>
    </>
  )
}
