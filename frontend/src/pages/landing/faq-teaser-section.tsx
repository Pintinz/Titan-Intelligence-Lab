import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { FaqAccordion } from '@/components/marketing/marketing-primitives'
import { Section, SectionHeading } from './section-primitives'

// The five highest-value questions from the full FAQ, kept accurate to current product state
// (not copied verbatim from faq-page.tsx, which still references self-service plan-switching that
// doesn't exist yet — see billing-page.tsx's own honest FAQ correction).
const FAQS = [
  {
    question: 'Is TitanIQ a betting site?',
    answer: 'No. We don\'t take bets, operate betting markets, or provide betting advice — see our Disclaimer for the full detail.',
  },
  {
    question: 'How accurate are the predictions?',
    answer: 'Accuracy varies by sport, market, and confidence level. Our Methodology page explains how confidence is calculated and calibrated, and the Learning Intelligence loop continuously re-evaluates predictions against real settled outcomes.',
  },
  {
    question: 'What sports does TitanIQ cover?',
    answer: 'Football, Basketball, Baseball, and Table Tennis today, each with its own Sport Intelligence Center.',
  },
  {
    question: 'Is there a free trial of Pro or Premium?',
    answer: 'No — Pro and Premium are billed as soon as you subscribe. The Free plan itself has no time limit, so you can explore before upgrading.',
  },
  {
    question: 'Does TitanIQ have an API?',
    answer: 'Yes — see the Developer Portal and API Reference for authentication, endpoints, and rate limits.',
  },
]

export function FaqTeaserSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <SectionHeading eyebrow="FAQ" title="Common questions" />
      <div className="max-w-2xl">
        <FaqAccordion items={FAQS} />
      </div>
      <Link
        to="/faq"
        className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary transition-colors hover:text-accent-primary"
      >
        See all FAQs <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
