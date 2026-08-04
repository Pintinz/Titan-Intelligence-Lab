import { Download, Check, X } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero } from '@/components/marketing/marketing-primitives'

const COLORS = [
  { name: 'Signal Teal', variable: '--color-accent-primary', hex: '#17E6B8', usage: 'Primary brand & interactive color; also high confidence' },
  { name: 'Premium Violet', variable: '--color-premium', hex: '#9B8CFF', usage: 'Reserved — peak confidence & premium-tier moments only' },
  { name: 'Live Crimson', variable: '--color-live', hex: '#FF5468', usage: 'Reserved — live match / alert status only' },
  { name: 'Carbon Background', variable: '--color-bg-primary', hex: '#06080D', usage: 'Primary dark surface' },
]

const DO_DONT = [
  { icon: Check, text: 'Use the mark on dark backgrounds with adequate clear space', good: true },
  { icon: Check, text: 'Preserve the mark\'s proportions when scaling', good: true },
  { icon: X, text: 'Recolor the mark outside the approved palette', good: false },
  { icon: X, text: 'Add effects (drop shadow, outline, gradient) to the logotype', good: false },
  { icon: X, text: 'Combine the TitanIQ mark with betting or gambling branding', good: false },
]

export default function BrandAssetsPage() {
  return (
    <>
      <Seo
        title="Brand Assets"
        description="TitanIQ brand guidelines — logo usage, color palette, typography, and downloadable assets."
        path="/brand-assets"
      />
      <PageHero
        eyebrow="Brand"
        title="Brand Assets"
        description="Guidelines for using the TitanIQ name, mark, and visual identity correctly."
      />

      <Section>
        <SectionHeading eyebrow="Logo" title="The mark" />
        <div className="flex flex-wrap gap-4">
          <div className="flex w-64 flex-col items-center justify-center gap-3 rounded-lg border border-border-default bg-bg-primary p-8">
            <span className="size-4 rounded-full bg-accent-primary" aria-hidden="true" />
            <span className="font-display text-lg font-semibold text-text-primary">TitanIQ</span>
          </div>
          <a
            href="/favicon.svg"
            download
            className="flex w-64 items-center justify-between rounded-lg border border-border-default bg-bg-elevated p-4 transition-colors hover:border-accent-primary/50"
          >
            <span className="text-sm font-medium text-text-primary">Download SVG mark</span>
            <Download className="size-4 text-accent-primary" aria-hidden="true" />
          </a>
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Color" title="Palette" description="Our signature-color discipline: one brand hue used for interaction and confidence, two rare accent colors reserved for specific meanings." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {COLORS.map((c) => (
            <div key={c.name} className="overflow-hidden rounded-lg border border-border-default bg-bg-elevated">
              <div className="h-20" style={{ backgroundColor: c.hex }} aria-hidden="true" />
              <div className="p-3">
                <p className="text-sm font-medium text-text-primary">{c.name}</p>
                <p className="font-mono text-xs text-text-muted">{c.hex}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{c.usage}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Typography" title="Type system" />
        <div className="space-y-4">
          <div>
            <p className="font-display text-3xl font-semibold text-text-primary">Display — headlines & branding</p>
            <p className="mt-1 text-xs text-text-muted font-mono">font-display</p>
          </div>
          <div>
            <p className="font-telemetry text-lg uppercase tracking-wider text-text-primary">Telemetry — confidence, badges, data labels</p>
            <p className="mt-1 text-xs text-text-muted font-mono">font-telemetry</p>
          </div>
          <div>
            <p className="text-lg text-text-primary">Body — copy, descriptions, UI text</p>
            <p className="mt-1 text-xs text-text-muted font-mono">font-body</p>
          </div>
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Usage" title="Do & don't" />
        <div className="grid gap-3 sm:grid-cols-2">
          {DO_DONT.map((item, i) => (
            <div key={i} className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4">
              <item.icon className={item.good ? 'mt-0.5 size-4 shrink-0 text-success' : 'mt-0.5 size-4 shrink-0 text-danger'} aria-hidden="true" />
              <p className="text-sm text-text-secondary">{item.text}</p>
            </div>
          ))}
        </div>
      </Section>
    </>
  )
}
