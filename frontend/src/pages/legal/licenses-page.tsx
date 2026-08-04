import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'open-source', label: 'Open-source attributions' },
  { id: 'data-licensing', label: 'Data provider licensing' },
  { id: 'api-terms', label: 'API license summary' },
]

const OSS_PACKAGES = [
  { name: 'React & React DOM', license: 'MIT' },
  { name: 'React Router', license: 'MIT' },
  { name: 'TanStack Query', license: 'MIT' },
  { name: 'Supabase JS Client', license: 'MIT' },
  { name: 'Zustand', license: 'MIT' },
  { name: 'Zod', license: 'MIT' },
  { name: 'React Hook Form', license: 'MIT' },
  { name: 'Tailwind CSS', license: 'MIT' },
  { name: 'Radix UI primitives', license: 'MIT' },
  { name: 'Lucide icons', license: 'ISC' },
  { name: 'class-variance-authority', license: 'Apache-2.0' },
  { name: 'clsx & tailwind-merge', license: 'MIT' },
]

export default function LicensesPage() {
  return (
    <>
      <Seo
        title="Licenses"
        description="Open-source software attributions and data licensing summary for TitanIQ."
        path="/licenses"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Licenses"
        summary="TitanIQ is built on open-source software and licensed sports data. This page attributes both."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            TitanIQ's software, predictions, Knowledge Graph, and TitanIQ-generated content are proprietary to
            Titan Intelligence Labs — see our <Link to="/copyright-policy" className="text-accent-primary hover:text-accent-primary-hover">Copyright Policy</Link>.
            The platform is built using open-source software, and displays sports data under license from
            third-party providers, both attributed below.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="open-source" title="Open-source attributions">
          <LegalParagraph>
            TitanIQ's frontend and infrastructure are built with the following major open-source projects, each
            used under its respective license:
          </LegalParagraph>
          <div className="overflow-x-auto rounded-lg border border-border-default">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead className="bg-bg-secondary/60 text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Project</th>
                  <th className="px-4 py-3 font-medium">License</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {OSS_PACKAGES.map((pkg) => (
                  <tr key={pkg.name}>
                    <td className="px-4 py-3 font-medium text-text-primary">{pkg.name}</td>
                    <td className="px-4 py-3 text-text-secondary">{pkg.license}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <LegalParagraph className="mt-3">
            This is a summary of major dependencies, not an exhaustive transitive dependency list. Full license
            texts are available on request at <a href="mailto:legal@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">legal@titaniq.ai</a>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="data-licensing" title="Data provider licensing">
          <LegalParagraph>
            Sports statistics, live scores, odds context, and news metadata displayed on TitanIQ are sourced under
            commercial license from third-party sports-data and news providers. We do not publicly name individual
            provider agreements for competitive and contractual reasons, but our sourcing and use of this data is
            governed by our <Link to="/editorial-policy" className="text-accent-primary hover:text-accent-primary-hover">Editorial Policy</Link> and{' '}
            <Link to="/copyright-policy" className="text-accent-primary hover:text-accent-primary-hover">Copyright Policy</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="api-terms" title="API license summary">
          <LegalParagraph>
            Access to the TitanIQ API is licensed, not sold — see the{' '}
            <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link> and{' '}
            <Link to="/acceptable-use" className="text-accent-primary hover:text-accent-primary-hover">Acceptable Use Policy</Link> for the terms governing
            what you can build with API output.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
