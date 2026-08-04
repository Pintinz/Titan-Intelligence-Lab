import { Link } from 'react-router-dom'
import { LifeBuoy, BookOpen, HelpCircle, Activity } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section } from '@/pages/landing/section-primitives'
import { PageHero, DocCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const RESOURCES = [
  { icon: BookOpen, title: 'Documentation', description: 'Guides for using every part of TitanIQ.', href: '/docs' },
  { icon: HelpCircle, title: 'FAQ', description: 'Quick answers to the questions we hear most.', href: '/faq' },
  { icon: LifeBuoy, title: 'Help Center', description: 'Browse support topics by category.', href: '/help' },
  { icon: Activity, title: 'System Status', description: 'Check for ongoing incidents before reporting an issue.', href: '/status' },
]

export default function SupportPage() {
  return (
    <>
      <Seo
        title="Support"
        description="Get help with TitanIQ — documentation, FAQ, the Help Center, or contact our support team directly."
        path="/support"
      />
      <PageHero
        eyebrow="Support"
        title="We're here to help."
        description="Most questions are answered in our docs and FAQ. For anything else, our support team typically responds within one business day."
        actions={
          <Button asChild size="lg">
            <a href="mailto:support@titaniq.ai">Email support@titaniq.ai</a>
          </Button>
        }
      />

      <Section>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {RESOURCES.map((r) => (
            <DocCard key={r.title} {...r} />
          ))}
        </div>
        <p className="mt-8 text-center text-sm text-text-secondary">
          Need a different team — enterprise sales, partnerships, or media? Visit our{' '}
          <Link to="/contact" className="text-accent-primary hover:text-accent-primary-hover">full Contact page</Link> to reach the right inbox directly.
        </p>
      </Section>
    </>
  )
}
