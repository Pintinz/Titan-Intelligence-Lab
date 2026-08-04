import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'ownership', label: 'TitanIQ ownership' },
  { id: 'licensed-content', label: 'Licensed third-party content' },
  { id: 'user-content', label: 'Your content' },
  { id: 'trademark', label: 'Trademark guidance' },
  { id: 'reporting', label: 'Reporting infringement' },
]

export default function CopyrightPolicyPage() {
  return (
    <>
      <Seo
        title="Copyright Policy"
        description="How copyright works on TitanIQ — what we own, what we license, what you retain, and how to report infringement."
        path="/copyright-policy"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Copyright Policy"
        summary="What TitanIQ owns, what we license from others, what you retain, and how to report a concern."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="ownership" title="TitanIQ ownership">
          <LegalParagraph>
            The TitanIQ name, logo, interface design, software, prediction models, confidence-scoring methodology,
            Knowledge Graph, and TitanIQ-generated summaries and graphics are the copyrighted and/or trademarked
            property of Titan Intelligence Labs, protected under applicable copyright and trademark law. Reproducing,
            redistributing, or creating derivative works from TitanIQ's original content without permission is
            prohibited — see our{' '}
            <Link to="/terms" className="text-accent-primary hover:text-accent-primary-hover">Terms of Service</Link> and{' '}
            <Link to="/acceptable-use" className="text-accent-primary hover:text-accent-primary-hover">Acceptable Use Policy</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="licensed-content" title="Licensed third-party content">
          <LegalParagraph>
            Sports data, statistics, and news metadata displayed on TitanIQ are sourced under license from
            third-party data and news providers, or from properly attributed public sources. Consistent with our{' '}
            <Link to="/editorial-policy" className="text-accent-primary hover:text-accent-primary-hover">Editorial Policy</Link>, we never reproduce full
            copyrighted news articles, and we never hotlink or reproduce a publisher's images without a license —
            imagery used alongside News Intelligence is either TitanIQ-generated or properly licensed. Open-source
            software components used to build TitanIQ are listed, with their licenses, on our{' '}
            <Link to="/licenses" className="text-accent-primary hover:text-accent-primary-hover">Licenses</Link> page.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="user-content" title="Your content">
          <LegalParagraph>
            You retain ownership of any content you submit to TitanIQ (such as feedback or saved configurations).
            By submitting it, you grant Titan Intelligence Labs a worldwide, non-exclusive, royalty-free license to
            use, store, and display it as necessary to operate and improve the Service.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="trademark" title="Trademark guidance">
          <LegalList
            items={[
              '"TitanIQ" and the TitanIQ logo may not be used to imply endorsement, affiliation, or partnership without our written permission.',
              'Team, league, and competition names and logos referenced on TitanIQ (e.g. in match cards) are the trademarks of their respective owners, used descriptively to identify the real-world fixtures our intelligence covers.',
              'Press and media may reference the TitanIQ name and use assets from our Press Kit and Brand Assets pages under the usage guidance provided there.',
            ]}
          />
        </LegalSection>

        <LegalSection id="reporting" title="Reporting infringement">
          <LegalParagraph>
            If you believe TitanIQ has used your copyrighted work without authorization, see our{' '}
            <Link to="/dmca" className="text-accent-primary hover:text-accent-primary-hover">DMCA Policy</Link> for how to submit a takedown notice.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
