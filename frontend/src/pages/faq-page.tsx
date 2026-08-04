import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, FaqAccordion } from '@/components/marketing/marketing-primitives'

const PRODUCT_FAQS = [
  { question: 'What is TitanIQ, exactly?', answer: 'TitanIQ is a sports intelligence platform. We turn live sports data, news, and community signal into explainable predictions and analysis across Football, Basketball, Baseball, and Table Tennis — every output ships with the evidence and confidence behind it.' },
  { question: 'Is TitanIQ a betting site?', answer: 'No. We don\'t take bets, operate betting markets, or provide betting advice. See our Disclaimer for the full detail.' },
  { question: 'How accurate are the predictions?', answer: 'Accuracy varies by sport, market, and confidence level — our Methodology page explains how we calculate and calibrate confidence, and our Learning Intelligence pipeline continuously evaluates predictions against real outcomes.' },
  { question: 'What sports does TitanIQ cover?', answer: 'Football, Basketball, Baseball, and Table Tennis today, each with its own Sport Intelligence Center. More sports are on our Roadmap.' },
]

const ACCOUNT_FAQS = [
  { question: 'How do I create an account?', answer: 'Click "Sign up" in the top navigation and follow the prompts — no credit card required for the Free tier.' },
  { question: 'Can I use TitanIQ without an account?', answer: 'You can browse our public pages, but live intelligence, predictions, and the dashboard require a free account.' },
  { question: 'How do I delete my account or data?', answer: 'Contact privacy@titaniq.ai to request account or data deletion — see our Privacy Policy for full detail on your rights.' },
]

const BILLING_FAQS = [
  { question: 'What plans does TitanIQ offer?', answer: 'Free, Pro, and Enterprise — see our Pricing page for the full comparison.' },
  { question: 'Can I cancel anytime?', answer: 'Yes, from account settings, effective at the end of your current billing period.' },
]

const DEVELOPER_FAQS = [
  { question: 'Does TitanIQ have an API?', answer: 'Yes — see our Developer Portal and API Reference for authentication, endpoints, and rate limits.' },
  { question: 'What are the API rate limits?', answer: 'Rate limits scale with your plan; documented limits are in the API Reference, and Enterprise plans can negotiate higher limits.' },
]

export default function FaqPage() {
  return (
    <>
      <Seo
        title="Frequently Asked Questions"
        description="Answers to common questions about TitanIQ — the product, accounts, billing, and the API."
        path="/faq"
      />
      <PageHero
        eyebrow="FAQ"
        title="Frequently asked questions"
        description="Can't find what you're looking for? Our Help Center and Support team are one click away."
      />

      <Section className="space-y-12">
        <div>
          <SectionHeading eyebrow="Product" title="About TitanIQ" />
          <div className="max-w-2xl"><FaqAccordion items={PRODUCT_FAQS} /></div>
        </div>
        <div>
          <SectionHeading eyebrow="Account" title="Accounts & privacy" />
          <div className="max-w-2xl"><FaqAccordion items={ACCOUNT_FAQS} /></div>
        </div>
        <div>
          <SectionHeading eyebrow="Billing" title="Plans & billing" />
          <div className="max-w-2xl"><FaqAccordion items={BILLING_FAQS} /></div>
        </div>
        <div>
          <SectionHeading eyebrow="Developers" title="API & integrations" />
          <div className="max-w-2xl"><FaqAccordion items={DEVELOPER_FAQS} /></div>
        </div>
      </Section>

      <Section className="border-t border-border-subtle text-center">
        <h2 className="font-display text-xl font-semibold text-text-primary">Still have questions?</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">
          Visit our <Link to="/help" className="text-accent-primary hover:text-accent-primary-hover">Help Center</Link> or{' '}
          <Link to="/support" className="text-accent-primary hover:text-accent-primary-hover">contact Support</Link>.
        </p>
      </Section>
    </>
  )
}
