import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'prohibited-conduct', label: 'Prohibited conduct' },
  { id: 'api-fair-use', label: 'API fair use' },
  { id: 'automated-access', label: 'Automated access & scraping' },
  { id: 'account-security', label: 'Account security obligations' },
  { id: 'enforcement', label: 'Enforcement' },
]

export default function AcceptableUsePage() {
  return (
    <>
      <Seo
        title="Acceptable Use Policy"
        description="Rules for acceptable use of TitanIQ's platform and API, including fair use and anti-abuse limits."
        path="/acceptable-use"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Acceptable Use Policy"
        summary="This policy defines what you can and can't do with TitanIQ. It's incorporated by reference into our Terms of Service."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            This Acceptable Use Policy applies to everyone who uses TitanIQ's website, application, or API. It
            works alongside our{' '}
            <Link to="/terms" className="text-accent-primary hover:text-accent-primary-hover">Terms of Service</Link>; violating this policy is a violation of
            those Terms.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="prohibited-conduct" title="Prohibited conduct">
          <LegalParagraph>You agree not to:</LegalParagraph>
          <LegalList
            items={[
              'Use TitanIQ for any unlawful purpose, or in violation of any applicable local, national, or international law.',
              'Attempt to gain unauthorized access to any account, system, or data, or probe/scan for vulnerabilities without authorization under our Security Policy.',
              'Interfere with or disrupt the integrity or performance of the Service — including denial-of-service attempts, or excessive requests intended to degrade availability for other users.',
              'Reverse-engineer, decompile, or attempt to extract the source code or underlying models of the Service, except where applicable law permits.',
              'Misrepresent TitanIQ predictions or confidence scores as guarantees, or use TitanIQ intelligence to facilitate fraud or deceptive practices.',
              'Use the Service to build a directly competing sports-prediction product using data or outputs obtained from TitanIQ.',
              'Upload malicious code or content that infringes on the rights of others.',
              'Use automated means to create accounts, or create accounts for the purpose of evading a suspension.',
            ]}
          />
        </LegalSection>

        <LegalSection id="api-fair-use" title="API fair use">
          <LegalParagraph>
            API access is subject to the rate limits and quotas described in the{' '}
            <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link> for your plan. Fair use means
            traffic patterns consistent with genuine application usage; we may throttle or suspend keys that exceed
            documented limits, that redistribute raw API responses to third parties outside your application without
            an enterprise redistribution agreement, or that are used to mirror or cache TitanIQ's dataset wholesale.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="automated-access" title="Automated access & scraping">
          <LegalParagraph>
            Automated scraping of TitanIQ's website (as opposed to using the documented API) is not permitted.
            Search engine and accessibility crawlers acting consistent with our robots directives are the
            exception, not automated data-collection tools competing with the API.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="account-security" title="Account security obligations">
          <LegalList
            items={[
              'Keep your credentials and API keys confidential; do not share them across unrelated parties.',
              'Rotate API keys promptly if you believe one has been exposed.',
              'Report suspected account compromise to security@titaniq.ai immediately.',
              'Enterprise customers are responsible for the conduct of users provisioned under their organization.',
            ]}
          />
        </LegalSection>

        <LegalSection id="enforcement" title="Enforcement">
          <LegalParagraph>
            Violations of this policy may result in warning, rate limiting, suspension, or termination of access,
            depending on severity, at our discretion, consistent with our{' '}
            <Link to="/terms" className="text-accent-primary hover:text-accent-primary-hover">Terms of Service</Link>. We may also take action required by law
            or to protect the security of the Service and its users.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
