import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalContactRow, LegalCallout } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'filing-notice', label: 'Filing a takedown notice' },
  { id: 'counter-notice', label: 'Counter-notice' },
  { id: 'repeat-infringers', label: 'Repeat infringer policy' },
  { id: 'agent', label: 'Designated agent' },
]

export default function DmcaPage() {
  return (
    <>
      <Seo
        title="DMCA Policy"
        description="TitanIQ's Digital Millennium Copyright Act takedown and counter-notice procedure."
        path="/dmca"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="DMCA Policy"
        summary="Titan Intelligence Labs respects intellectual property rights and responds to properly submitted copyright takedown notices."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            We respond to notices of alleged copyright infringement that comply with the U.S. Digital Millennium
            Copyright Act ("DMCA") and analogous laws in other jurisdictions. This policy describes how to submit a
            notice and how we handle it.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="filing-notice" title="Filing a takedown notice">
          <LegalParagraph>To submit a takedown notice, send the following to our designated agent below:</LegalParagraph>
          <LegalList
            ordered
            items={[
              'A physical or electronic signature of the copyright owner or a person authorized to act on their behalf.',
              'Identification of the copyrighted work claimed to have been infringed.',
              'Identification of the material claimed to be infringing, with enough detail (e.g. a URL) for us to locate it.',
              'Your contact information — address, telephone number, and email address.',
              'A statement that you have a good-faith belief the use is not authorized by the copyright owner, its agent, or the law.',
              'A statement, made under penalty of perjury, that the information in the notice is accurate and that you are authorized to act on the copyright owner\'s behalf.',
            ]}
          />
          <LegalCallout tone="warning">
            Submitting a false claim may expose you to liability for damages. If you're unsure whether material
            infringes your copyright, consider consulting a legal advisor before filing a notice.
          </LegalCallout>
        </LegalSection>

        <LegalSection id="counter-notice" title="Counter-notice">
          <LegalParagraph>
            If content you posted was removed in response to a takedown notice and you believe it was removed in
            error, you may submit a counter-notice containing your identification of the removed material, a
            statement under penalty of perjury that you have a good-faith belief the material was removed by
            mistake or misidentification, your consent to the jurisdiction described in our{' '}
            <a href="/terms" className="text-accent-primary hover:text-accent-primary-hover">Terms of Service</a>, and your physical or electronic signature.
            We may restore the material after a statutory waiting period unless the original complainant files a
            court action.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="repeat-infringers" title="Repeat infringer policy">
          <LegalParagraph>
            We terminate, in appropriate circumstances, the accounts of users determined to be repeat infringers of
            others' intellectual property rights.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="agent" title="Designated agent">
          <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
            <LegalContactRow label="DMCA notices" value="dmca@titaniq.ai" href="mailto:dmca@titaniq.ai" />
            <LegalContactRow label="Entity" value="Titan Intelligence Labs, Copyright Agent" />
          </div>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
