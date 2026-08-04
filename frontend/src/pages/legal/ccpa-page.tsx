import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalContactRow } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'categories', label: 'Categories of information we collect' },
  { id: 'right-to-know', label: 'Right to know' },
  { id: 'right-to-delete', label: 'Right to delete' },
  { id: 'right-to-correct', label: 'Right to correct' },
  { id: 'opt-out', label: 'Right to opt out of sale/sharing' },
  { id: 'non-discrimination', label: 'Right to non-discrimination' },
  { id: 'authorized-agent', label: 'Authorized agents' },
  { id: 'contact', label: 'Contact us' },
]

const CATEGORIES = [
  'Identifiers (name, email address, account ID)',
  'Account and authentication information',
  'Commercial information (subscription plan, billing history)',
  'Internet/network activity (pages viewed, features used, log data)',
  'Geolocation data (approximate, derived from IP address)',
]

export default function CcpaPage() {
  return (
    <>
      <Seo
        title="CCPA Compliance"
        description="TitanIQ's compliance with the California Consumer Privacy Act, including your rights as a California resident."
        path="/ccpa"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="CCPA Compliance"
        summary="Rights available to California residents under the California Consumer Privacy Act (CCPA), as amended by the California Privacy Rights Act (CPRA)."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            This page supplements our{' '}
            <Link to="/privacy" className="text-accent-primary hover:text-accent-primary-hover">Privacy Policy</Link> for California residents, describing
            the categories of personal information we collect and the rights the CCPA gives you over it.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="categories" title="Categories of information we collect">
          <LegalList items={CATEGORIES} />
          <LegalParagraph className="mt-3">
            We collect these categories for the business purposes described in our{' '}
            <Link to="/privacy" className="text-accent-primary hover:text-accent-primary-hover">Privacy Policy</Link> — operating your account, providing
            the Service, security, and support.{' '}
            <strong className="text-text-primary">We do not sell personal information</strong>, and we do not
            "share" it for cross-context behavioral advertising as those terms are defined under the CCPA.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="right-to-know" title="Right to know">
          <LegalParagraph>
            You can request that we disclose the categories and specific pieces of personal information we've
            collected about you, the categories of sources, the business purpose for collecting it, and the
            categories of third parties (if any) we've disclosed it to, covering the preceding 12 months.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="right-to-delete" title="Right to delete">
          <LegalParagraph>
            You can request deletion of personal information we've collected from you, subject to exceptions the
            CCPA permits — for example, information we need to complete a transaction, detect security incidents,
            or comply with a legal obligation.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="right-to-correct" title="Right to correct">
          <LegalParagraph>
            You can request that we correct inaccurate personal information we maintain about you.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="opt-out" title="Right to opt out of sale/sharing">
          <LegalParagraph>
            Because we do not sell or share personal information as defined by the CCPA, there is currently no
            "Do Not Sell or Share My Personal Information" opt-out required. If this changes — for example, if
            advertising cookies covered by our{' '}
            <Link to="/advertising-policy" className="text-accent-primary hover:text-accent-primary-hover">Advertising Policy</Link> are activated in a way
            that constitutes "sharing" under the CCPA — we will add an opt-out mechanism here before that change
            takes effect.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="non-discrimination" title="Right to non-discrimination">
          <LegalParagraph>
            We will not deny you goods or services, charge different prices, or provide a different level of
            service because you exercised a CCPA right.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="authorized-agent" title="Authorized agents">
          <LegalParagraph>
            You may designate an authorized agent to submit a CCPA request on your behalf. We may require proof of
            the agent's authorization and independent verification of your identity before fulfilling the request.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="contact" title="Contact us">
          <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
            <LegalContactRow label="California privacy requests" value="privacy@titaniq.ai" href="mailto:privacy@titaniq.ai" />
          </div>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
