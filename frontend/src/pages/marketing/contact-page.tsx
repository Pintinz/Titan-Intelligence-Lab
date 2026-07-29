import { Mail } from 'lucide-react'
import { MarketingArticle, ArticleSection } from '@/components/layout/marketing-article'

const CONTACT_EMAIL = 'info.autotechub@gmail.com'

/** Real contact channel only — no fabricated contact-form submission (no backend endpoint for
 * one exists), and no invented support address. */
export default function ContactPage() {
  return (
    <MarketingArticle eyebrow="Contact" title="Get in touch">
      <ArticleSection title="Email">
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="inline-flex w-fit items-center gap-2 rounded-md border border-border-default bg-bg-elevated px-4 py-2 text-text-primary hover:border-border-strong"
        >
          <Mail className="h-4 w-4" aria-hidden="true" />
          {CONTACT_EMAIL}
        </a>
      </ArticleSection>
    </MarketingArticle>
  )
}
