import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalContactRow } from '@/components/marketing/legal-layout'
import { Link } from 'react-router-dom'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'information-we-collect', label: 'Information we collect' },
  { id: 'how-we-use-information', label: 'How we use information' },
  { id: 'legal-bases', label: 'Legal bases for processing' },
  { id: 'cookies-tracking', label: 'Cookies & tracking' },
  { id: 'data-sharing', label: 'How we share information' },
  { id: 'data-retention', label: 'Data retention' },
  { id: 'your-rights', label: 'Your privacy rights' },
  { id: 'international-transfers', label: 'International transfers' },
  { id: 'childrens-privacy', label: "Children's privacy" },
  { id: 'security', label: 'How we protect your data' },
  { id: 'changes', label: 'Changes to this policy' },
  { id: 'contact', label: 'Contact us' },
]

export default function PrivacyPolicyPage() {
  return (
    <>
      <Seo
        title="Privacy Policy"
        description="How TitanIQ collects, uses, shares, and protects your personal information, including your rights under GDPR and CCPA."
        path="/privacy"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Privacy Policy"
        summary="This Privacy Policy explains what personal information Titan Intelligence Labs collects when you use TitanIQ, why we collect it, how it's used, and the rights you have over it."
        lastUpdated="July 29, 2026"
        effectiveDate="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            TitanIQ ("TitanIQ," "we," "us," or "our") is a sports intelligence platform operated by Titan
            Intelligence Labs. This policy applies to titaniq.ai, the TitanIQ web application, our API, and any
            future TitanIQ mobile applications (collectively, the "Service"). It describes our practices for
            collecting, using, and safeguarding information from visitors and registered users.
          </LegalParagraph>
          <LegalParagraph>
            TitanIQ is a sports intelligence and analytics product, not a betting or gambling service. We do not
            collect payment-card data for wagering purposes, and nothing in the Service constitutes financial or
            gambling advice — see our <Link to="/disclaimer" className="text-accent-primary hover:text-accent-primary-hover">Disclaimer</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="information-we-collect" title="Information we collect">
          <LegalParagraph>We collect information in three ways:</LegalParagraph>
          <LegalList
            items={[
              <>
                <strong className="text-text-primary">Information you provide.</strong> Account details (name,
                email address, password hash — TitanIQ never stores plaintext passwords), profile preferences,
                subscription and billing details processed by our payment provider, support requests, and any
                content you submit (e.g. saved watchlists, feedback).
              </>,
              <>
                <strong className="text-text-primary">Information collected automatically.</strong> Device and
                browser type, IP address, approximate location derived from IP, pages visited, features used,
                referring URLs, and timestamps — collected via server logs and, where you consent, analytics
                cookies. See our <Link to="/cookies" className="text-accent-primary hover:text-accent-primary-hover">Cookie Policy</Link>.
              </>,
              <>
                <strong className="text-text-primary">Information from third parties.</strong> If you sign in
                with Google, we receive the profile fields Google shares with your consent (name, email, profile
                image). Sports data, odds, and news metadata we process about matches, teams, and competitions is
                not personal information about you.
              </>,
            ]}
          />
        </LegalSection>

        <LegalSection id="how-we-use-information" title="How we use information">
          <LegalList
            items={[
              'To create and secure your account and authenticate you (via Supabase Auth, our identity provider).',
              'To operate the Service — generating and displaying predictions, confidence scores, and intelligence relevant to your saved preferences.',
              'To process subscription payments and send billing communications.',
              'To respond to support requests and security reports.',
              'To monitor, debug, and improve platform reliability and performance.',
              'To detect, investigate, and prevent fraud, abuse, and security incidents.',
              'To send service communications (required) and product updates (optional, with an unsubscribe option).',
              'To comply with legal obligations and enforce our Terms of Service.',
            ]}
          />
        </LegalSection>

        <LegalSection id="legal-bases" title="Legal bases for processing (EEA/UK users)">
          <LegalParagraph>
            Where the General Data Protection Regulation applies, we rely on the following legal bases: performance
            of a contract (operating your account and the Service), legitimate interests (security, fraud
            prevention, and product improvement, balanced against your rights), consent (analytics and marketing
            cookies, which you can withdraw at any time), and legal obligation (tax, accounting, and regulatory
            recordkeeping). See our <Link to="/gdpr" className="text-accent-primary hover:text-accent-primary-hover">GDPR Compliance</Link> page for more detail.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="cookies-tracking" title="Cookies & tracking">
          <LegalParagraph>
            We use essential cookies to operate the Service (session, authentication, security) and, with your
            consent, analytics cookies to understand how the Service is used. TitanIQ is built to support Google
            AdSense on public pages and Google AdMob in a future mobile app; if and when advertising is enabled,
            consent-gated advertising cookies will be added and disclosed here and in our{' '}
            <Link to="/cookies" className="text-accent-primary hover:text-accent-primary-hover">Cookie Policy</Link> before they are set. Full detail on cookie
            categories, purposes, and how to manage your preferences lives in that policy.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="data-sharing" title="How we share information">
          <LegalParagraph>We do not sell your personal information. We share it only with:</LegalParagraph>
          <LegalList
            items={[
              <><strong className="text-text-primary">Service providers</strong> who process data on our behalf under contract — hosting, database, authentication, analytics, email delivery, and payment processing vendors.</>,
              <><strong className="text-text-primary">Legal and safety</strong> disclosures where required by law, subpoena, or to protect the rights, property, or safety of TitanIQ, our users, or the public.</>,
              <><strong className="text-text-primary">Business transfers</strong> — if Titan Intelligence Labs is involved in a merger, acquisition, or asset sale, information may transfer as part of that transaction, subject to this policy's continued protections.</>,
              <><strong className="text-text-primary">With your direction</strong> — for example, if you connect a third-party integration via our API.</>,
            ]}
          />
        </LegalSection>

        <LegalSection id="data-retention" title="Data retention">
          <LegalParagraph>
            We retain account information for as long as your account is active and for a limited period afterward
            to comply with legal, tax, and dispute-resolution obligations, after which it is deleted or anonymized.
            Server logs are retained for a rolling window sufficient for security monitoring and then purged.
            You may request earlier deletion — see "Your privacy rights" below.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="your-rights" title="Your privacy rights">
          <LegalParagraph>
            Depending on where you live, you may have the right to access, correct, export, or delete your personal
            information; to restrict or object to certain processing; and to withdraw consent at any time. California
            residents have additional rights described in our{' '}
            <Link to="/ccpa" className="text-accent-primary hover:text-accent-primary-hover">CCPA Compliance</Link> page; EEA/UK residents have rights described
            in our <Link to="/gdpr" className="text-accent-primary hover:text-accent-primary-hover">GDPR Compliance</Link> page. To exercise any of these rights,
            contact <a href="mailto:privacy@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">privacy@titaniq.ai</a> — we verify
            requests and respond within the timeframe required by applicable law.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="international-transfers" title="International transfers">
          <LegalParagraph>
            TitanIQ's infrastructure providers may process data in countries other than your own. Where we transfer
            personal information out of the EEA, UK, or Switzerland, we rely on recognized transfer mechanisms such
            as Standard Contractual Clauses with our processors.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="childrens-privacy" title="Children's privacy">
          <LegalParagraph>
            TitanIQ is not directed to children under 16, and we do not knowingly collect personal information from
            them. If you believe a child has provided us with personal information, contact us and we will delete
            it promptly.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="security" title="How we protect your data">
          <LegalParagraph>
            We use encryption in transit and at rest, role-based access control, and continuous monitoring to
            protect your information. No system is perfectly secure — see our{' '}
            <Link to="/security-policy" className="text-accent-primary hover:text-accent-primary-hover">Security Policy</Link> for detail on our practices and how
            to report a vulnerability.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="changes" title="Changes to this policy">
          <LegalParagraph>
            We'll update the "Last updated" date above whenever this policy changes, and for material changes we'll
            provide a more prominent notice (such as an in-app banner or email) before the change takes effect.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="contact" title="Contact us">
          <LegalParagraph>Questions about this policy or your data can be directed to:</LegalParagraph>
          <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
            <LegalContactRow label="Privacy inquiries" value="privacy@titaniq.ai" href="mailto:privacy@titaniq.ai" />
            <LegalContactRow label="General legal" value="legal@titaniq.ai" href="mailto:legal@titaniq.ai" />
            <LegalContactRow label="Entity" value="Titan Intelligence Labs" />
          </div>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
