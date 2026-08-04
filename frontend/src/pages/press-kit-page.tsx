import { useState } from 'react'
import { Download, Copy, Check } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const BOILERPLATE = `TitanIQ is a sports intelligence platform built by Titan Intelligence Labs that converts live sports data, structured intelligence, news, and community signals into explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis. Unlike betting tips or score apps, every TitanIQ prediction ships with visible evidence and a calibrated confidence score — predictions are one output, not the point.`

const FACTS = [
  ['Founded', 'Titan Intelligence Labs'],
  ['Product', 'TitanIQ — Sports Intelligence Platform'],
  ['Coverage', 'Football, Basketball, Baseball, Table Tennis'],
  ['Category', 'Sports intelligence & analytics (not a betting service)'],
  ['Press contact', 'press@titaniq.ai'],
]

export default function PressKitPage() {
  const [copied, setCopied] = useState(false)

  async function copyBoilerplate() {
    await navigator.clipboard.writeText(BOILERPLATE)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <Seo
        title="Press Kit"
        description="TitanIQ press kit — company boilerplate, key facts, logo assets, and media contact."
        path="/press-kit"
      />
      <PageHero
        eyebrow="Press"
        title="Press Kit"
        description="Boilerplate, key facts, and brand assets for journalists and media covering TitanIQ."
        actions={
          <Button asChild size="lg">
            <a href="mailto:press@titaniq.ai">Contact press@titaniq.ai</a>
          </Button>
        }
      />

      <Section>
        <SectionHeading eyebrow="Boilerplate" title="Company description" />
        <div className="max-w-2xl rounded-lg border border-border-default bg-bg-elevated p-5">
          <p className="text-sm leading-relaxed text-text-secondary">{BOILERPLATE}</p>
          <Button variant="secondary" size="sm" className="mt-4" onClick={copyBoilerplate}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? 'Copied' : 'Copy text'}
          </Button>
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Facts" title="Key facts" />
        <dl className="max-w-2xl divide-y divide-border-subtle rounded-lg border border-border-default bg-bg-elevated px-5">
          {FACTS.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-4 py-3 text-sm">
              <dt className="text-text-muted">{label}</dt>
              <dd className="text-right font-medium text-text-primary">{value}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Assets" title="Logo & icon downloads" description="Full brand guidelines live on the Brand Assets page." />
        <div className="grid gap-4 sm:grid-cols-2">
          <a
            href="/favicon.svg"
            download
            className="flex items-center justify-between rounded-lg border border-border-default bg-bg-elevated p-4 transition-colors hover:border-accent-primary/50"
          >
            <div>
              <p className="text-sm font-medium text-text-primary">TitanIQ Mark (SVG)</p>
              <p className="text-xs text-text-muted">Scalable vector, transparent background</p>
            </div>
            <Download className="size-4 text-accent-primary" aria-hidden="true" />
          </a>
          <a
            href="/pwa-icon.svg"
            download
            className="flex items-center justify-between rounded-lg border border-border-default bg-bg-elevated p-4 transition-colors hover:border-accent-primary/50"
          >
            <div>
              <p className="text-sm font-medium text-text-primary">TitanIQ App Icon (SVG)</p>
              <p className="text-xs text-text-muted">Square icon mark</p>
            </div>
            <Download className="size-4 text-accent-primary" aria-hidden="true" />
          </a>
        </div>
      </Section>
    </>
  )
}
