import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalContactRow, LegalCallout } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'infrastructure', label: 'Infrastructure' },
  { id: 'encryption', label: 'Encryption' },
  { id: 'authentication', label: 'Authentication' },
  { id: 'access-control', label: 'Access control (RBAC)' },
  { id: 'monitoring', label: 'Monitoring & logging' },
  { id: 'vulnerability-disclosure', label: 'Vulnerability disclosure' },
  { id: 'incident-response', label: 'Incident response' },
  { id: 'contact', label: 'Contact us' },
]

export default function SecurityPolicyPage() {
  return (
    <>
      <Seo
        title="Security Policy"
        description="How TitanIQ secures its infrastructure, authenticates users, and responds to vulnerability reports and incidents."
        path="/security-policy"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Security Policy"
        summary="Security is a precondition for trust in an intelligence platform. This is how we approach it."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            This policy summarizes the technical and organizational measures Titan Intelligence Labs uses to
            protect TitanIQ and the data it processes. For a broader view of security alongside privacy,
            compliance, and infrastructure, see our{' '}
            <Link to="/trust-center" className="text-accent-primary hover:text-accent-primary-hover">Trust Center</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="infrastructure" title="Infrastructure">
          <LegalParagraph>
            TitanIQ runs on managed cloud infrastructure with network isolation between environments, automated
            patching of underlying platform components, and infrastructure-as-code deployments so environments stay
            consistent and auditable. Production access is restricted to authorized personnel.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="encryption" title="Encryption">
          <LegalList
            items={[
              'Data in transit is encrypted via TLS on every connection between clients, our application, and our API.',
              'Data at rest — including account data and stored predictions — is encrypted at the storage layer.',
              'Passwords are never stored in plaintext; authentication credentials are hashed using industry-standard algorithms.',
              'API keys and secrets are stored in a managed secrets store, never committed to source control.',
            ]}
          />
        </LegalSection>

        <LegalSection id="authentication" title="Authentication">
          <LegalParagraph>
            User authentication is handled by a dedicated, industry-standard identity provider issuing short-lived
            JSON Web Tokens (JWTs) that are validated on every API request. This keeps authentication logic isolated
            from application logic and lets us apply session expiry, token revocation, and (where enabled) social
            sign-in consistently across the platform.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="access-control" title="Access control (RBAC)">
          <LegalParagraph>
            TitanIQ enforces role-based access control (RBAC) throughout the platform — including administrator-only
            surfaces such as the Operations Center — so that a user's permissions are checked against their role on
            every request, both in the interface and at the API layer, not just hidden in the UI.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="monitoring" title="Monitoring & logging">
          <LegalParagraph>
            We log authentication events, administrative actions, and API activity to support security monitoring,
            anomaly detection, and post-incident investigation, retained consistent with our{' '}
            <Link to="/privacy" className="text-accent-primary hover:text-accent-primary-hover">Privacy Policy</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="vulnerability-disclosure" title="Vulnerability disclosure">
          <LegalCallout tone="info">
            If you believe you've found a security vulnerability in TitanIQ, please report it to{' '}
            <a href="mailto:security@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">security@titaniq.ai</a> with enough detail
            to reproduce it. We ask that you give us a reasonable window to investigate and remediate before public
            disclosure, that you avoid accessing or modifying data that isn't yours, and that you avoid degrading
            the Service for other users. We do not pursue legal action against good-faith security research
            conducted consistent with this policy.
          </LegalCallout>
        </LegalSection>

        <LegalSection id="incident-response" title="Incident response">
          <LegalParagraph>
            We maintain an internal incident response process covering triage, containment, remediation, and
            post-incident review. Where a security incident affects personal information, we will notify affected
            users and, where legally required, relevant regulators, within the timeframe applicable law requires.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="contact" title="Contact us">
          <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
            <LegalContactRow label="Report a vulnerability" value="security@titaniq.ai" href="mailto:security@titaniq.ai" />
            <LegalContactRow label="General security questions" value="security@titaniq.ai" href="mailto:security@titaniq.ai" />
          </div>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
