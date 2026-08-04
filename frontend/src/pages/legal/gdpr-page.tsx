import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalContactRow } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'data-controller', label: 'Data controller' },
  { id: 'legal-bases', label: 'Legal bases' },
  { id: 'your-rights', label: 'Your GDPR rights' },
  { id: 'exercising-rights', label: 'Exercising your rights' },
  { id: 'transfers', label: 'International data transfers' },
  { id: 'dpo', label: 'Data protection contact' },
  { id: 'retention', label: 'Data retention' },
]

const RIGHTS = [
  { name: 'Right to access', description: 'Request a copy of the personal information we hold about you.' },
  { name: 'Right to rectification', description: 'Ask us to correct inaccurate or incomplete information.' },
  { name: 'Right to erasure', description: 'Ask us to delete your personal information, subject to legal retention requirements.' },
  { name: 'Right to restrict processing', description: 'Ask us to limit how we use your information in certain circumstances.' },
  { name: 'Right to data portability', description: 'Receive your data in a structured, machine-readable format, or have it transmitted to another provider.' },
  { name: 'Right to object', description: 'Object to processing based on legitimate interests, including for direct marketing.' },
  { name: 'Right to withdraw consent', description: 'Withdraw consent at any time for processing that relies on it, such as analytics cookies.' },
  { name: 'Right to lodge a complaint', description: 'Complain to your local data protection authority if you believe we have not handled your data lawfully.' },
]

export default function GdprPage() {
  return (
    <>
      <Seo
        title="GDPR Compliance"
        description="TitanIQ's compliance with the EU General Data Protection Regulation, including your rights as a data subject."
        path="/gdpr"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="GDPR Compliance"
        summary="How TitanIQ processes personal information consistent with the EU/UK General Data Protection Regulation, and the rights available to you as a data subject."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            If you are located in the European Economic Area, the United Kingdom, or Switzerland, the General Data
            Protection Regulation ("GDPR") and equivalent UK legislation apply to our processing of your personal
            information. This page supplements our{' '}
            <Link to="/privacy" className="text-accent-primary hover:text-accent-primary-hover">Privacy Policy</Link> with GDPR-specific detail.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="data-controller" title="Data controller">
          <LegalParagraph>
            Titan Intelligence Labs is the data controller for personal information processed through TitanIQ's
            website, application, and API.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="legal-bases" title="Legal bases">
          <LegalParagraph>
            We process personal information under the following legal bases: contract performance (operating your
            account), legitimate interests (security, fraud prevention, and improving the Service — balanced
            against your rights and freedoms), consent (analytics and, when active, marketing cookies), and legal
            obligation (tax, accounting, and regulatory recordkeeping).
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="your-rights" title="Your GDPR rights">
          <div className="grid gap-3 sm:grid-cols-2">
            {RIGHTS.map((right) => (
              <div key={right.name} className="rounded-lg border border-border-default bg-bg-elevated p-4">
                <p className="font-display text-sm font-semibold text-text-primary">{right.name}</p>
                <p className="mt-1 text-sm leading-relaxed text-text-secondary">{right.description}</p>
              </div>
            ))}
          </div>
        </LegalSection>

        <LegalSection id="exercising-rights" title="Exercising your rights">
          <LegalParagraph>
            To exercise any of the rights above, email{' '}
            <a href="mailto:privacy@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">privacy@titaniq.ai</a>. We may need to
            verify your identity before actioning a request, and we will respond within one month as required by
            the GDPR (extendable by two further months for complex requests, with notice to you).
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="transfers" title="International data transfers">
          <LegalParagraph>
            Where personal information is transferred outside the EEA, UK, or Switzerland — for example, to a
            hosting or infrastructure provider — we rely on recognized safeguards such as the European
            Commission's Standard Contractual Clauses, or an adequacy decision, to ensure your data remains
            protected.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="dpo" title="Data protection contact">
          <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
            <LegalContactRow label="Data protection inquiries" value="privacy@titaniq.ai" href="mailto:privacy@titaniq.ai" />
          </div>
        </LegalSection>

        <LegalSection id="retention" title="Data retention">
          <LegalList
            items={[
              'Account data is retained for as long as your account is active, plus a limited period for legal and dispute-resolution purposes.',
              'You may request deletion at any time; we will honor it unless we have an overriding legal obligation to retain specific records.',
              'Security and audit logs are retained on a rolling basis sufficient for their security purpose.',
            ]}
          />
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
