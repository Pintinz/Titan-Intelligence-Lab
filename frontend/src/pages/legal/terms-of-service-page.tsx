import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalCallout } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'acceptance', label: 'Acceptance of terms' },
  { id: 'eligibility', label: 'Eligibility' },
  { id: 'accounts', label: 'Account registration' },
  { id: 'subscriptions', label: 'Subscriptions & billing' },
  { id: 'acceptable-use', label: 'Acceptable use' },
  { id: 'intellectual-property', label: 'Intellectual property' },
  { id: 'predictions-disclaimer', label: 'Predictions are not advice' },
  { id: 'api-usage', label: 'API access' },
  { id: 'termination', label: 'Suspension & termination' },
  { id: 'disclaimers', label: 'Disclaimers' },
  { id: 'liability', label: 'Limitation of liability' },
  { id: 'indemnification', label: 'Indemnification' },
  { id: 'governing-law', label: 'Governing law & disputes' },
  { id: 'changes', label: 'Changes to these terms' },
  { id: 'contact', label: 'Contact us' },
]

export default function TermsOfServicePage() {
  return (
    <>
      <Seo
        title="Terms of Service"
        description="The terms governing your use of TitanIQ's website, application, and API."
        path="/terms"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Terms of Service"
        summary="These Terms govern your access to and use of TitanIQ. By creating an account or using the Service, you agree to them."
        lastUpdated="July 29, 2026"
        effectiveDate="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="acceptance" title="Acceptance of terms">
          <LegalParagraph>
            These Terms of Service ("Terms") form a binding agreement between you and Titan Intelligence Labs
            ("TitanIQ," "we," "us") governing your use of titaniq.ai, the TitanIQ application, and the TitanIQ API
            (together, the "Service"). By creating an account, or by accessing or using the Service in any way, you
            agree to be bound by these Terms and by our{' '}
            <Link to="/privacy" className="text-accent-primary hover:text-accent-primary-hover">Privacy Policy</Link>. If you do not agree, do not use the
            Service.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="eligibility" title="Eligibility">
          <LegalParagraph>
            You must be at least 16 years old to use TitanIQ. By using the Service you represent that you meet this
            requirement and that you have the legal capacity to enter into these Terms. If you use the Service on
            behalf of an organization, you represent that you're authorized to bind that organization.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="accounts" title="Account registration">
          <LegalList
            items={[
              'You must provide accurate, current information when creating an account and keep it up to date.',
              'You are responsible for safeguarding your credentials and for all activity under your account.',
              'Notify us immediately at security@titaniq.ai if you suspect unauthorized access to your account.',
              'One account per person unless an enterprise agreement explicitly permits shared or service accounts.',
            ]}
          />
        </LegalSection>

        <LegalSection id="subscriptions" title="Subscriptions & billing">
          <LegalParagraph>
            Some features require a paid subscription. Pricing and plan features are described on our{' '}
            <Link to="/pricing" className="text-accent-primary hover:text-accent-primary-hover">Pricing</Link> page. Unless stated otherwise, subscriptions renew
            automatically for successive billing periods until cancelled. You can cancel at any time from account
            settings; cancellation takes effect at the end of the current billing period, and fees already paid are
            non-refundable except where required by law. We may change subscription pricing with at least 30 days'
            notice before it applies to your next renewal. Enterprise API access is governed by a separate order
            form or enterprise agreement where one is in place, which controls over these Terms for that access.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="acceptable-use" title="Acceptable use">
          <LegalParagraph>
            Full detail lives in our <Link to="/acceptable-use" className="text-accent-primary hover:text-accent-primary-hover">Acceptable Use Policy</Link>, which is incorporated into these Terms by reference. In summary, you agree not to
            misuse the Service — including scraping beyond documented API limits, reverse-engineering the platform,
            interfering with its operation, or using it to build a directly competing product from our data.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="intellectual-property" title="Intellectual property">
          <LegalParagraph>
            The Service — including its software, design, predictions, confidence models, Knowledge Graph, and
            TitanIQ-generated summaries — is owned by Titan Intelligence Labs and protected by intellectual property
            law. We grant you a limited, non-exclusive, non-transferable license to access and use the Service for
            its intended purpose. You retain ownership of any content you submit, and grant us a license to use it
            to operate and improve the Service. See our{' '}
            <Link to="/copyright-policy" className="text-accent-primary hover:text-accent-primary-hover">Copyright Policy</Link> and{' '}
            <Link to="/licenses" className="text-accent-primary hover:text-accent-primary-hover">Licenses</Link> pages for more detail, including third-party
            attributions.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="predictions-disclaimer" title="Predictions are not advice">
          <LegalCallout tone="warning">
            TitanIQ's predictions, confidence scores, and intelligence outputs are probabilistic estimates generated
            from historical and live data. They are provided for informational and entertainment purposes only —
            they are not betting advice, financial advice, or a guarantee of any outcome. You are solely responsible
            for decisions you make based on information from the Service. See our full{' '}
            <Link to="/disclaimer" className="text-accent-primary hover:text-accent-primary-hover">Disclaimer</Link>.
          </LegalCallout>
        </LegalSection>

        <LegalSection id="api-usage" title="API access">
          <LegalParagraph>
            Developer and enterprise API access is subject to the rate limits, authentication requirements, and
            usage restrictions described in the{' '}
            <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link> and{' '}
            <Link to="/developers" className="text-accent-primary hover:text-accent-primary-hover">Developer Portal</Link>. We may throttle, suspend, or revoke
            API keys that exceed documented limits or violate these Terms.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="termination" title="Suspension & termination">
          <LegalParagraph>
            You may stop using the Service and delete your account at any time from account settings. We may
            suspend or terminate your access if you materially breach these Terms, misuse the Service, or where
            required by law, generally with notice unless the conduct poses an immediate risk to the Service or
            other users. Provisions that by their nature should survive termination (ownership, disclaimers,
            limitation of liability, governing law) will survive.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="disclaimers" title="Disclaimers">
          <LegalParagraph>
            The Service is provided "as is" and "as available" without warranties of any kind, express or implied,
            including merchantability, fitness for a particular purpose, and non-infringement. We do not warrant
            that the Service will be uninterrupted, error-free, or that predictions will be accurate.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="liability" title="Limitation of liability">
          <LegalParagraph>
            To the maximum extent permitted by law, Titan Intelligence Labs will not be liable for any indirect,
            incidental, special, consequential, or punitive damages, or for lost profits or data, arising from your
            use of the Service. Our total liability for any claim arising from these Terms or the Service will not
            exceed the amount you paid us in the twelve months preceding the claim, or one hundred U.S. dollars if
            you have not made any payment.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="indemnification" title="Indemnification">
          <LegalParagraph>
            You agree to indemnify and hold Titan Intelligence Labs harmless from claims, damages, and expenses
            (including reasonable legal fees) arising from your misuse of the Service or violation of these Terms.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="governing-law" title="Governing law & disputes">
          <LegalParagraph>
            These Terms are governed by the laws of the jurisdiction in which Titan Intelligence Labs is
            incorporated, without regard to conflict-of-law principles. Any dispute not resolved informally will be
            subject to the exclusive jurisdiction of the courts of that jurisdiction, except where applicable
            consumer-protection law grants you the right to bring a claim in your own jurisdiction.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="changes" title="Changes to these terms">
          <LegalParagraph>
            We may update these Terms from time to time. We'll update the "Last updated" date and, for material
            changes, provide reasonable advance notice. Continued use of the Service after changes take effect
            constitutes acceptance of the updated Terms.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="contact" title="Contact us">
          <LegalParagraph>
            Questions about these Terms can be sent to{' '}
            <a href="mailto:legal@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">legal@titaniq.ai</a>.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
