import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList, LegalCallout } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'overview', label: 'Overview' },
  { id: 'how-ads-display', label: 'How ads are displayed' },
  { id: 'sponsored-content', label: 'Sponsored content rules' },
  { id: 'editorial-independence', label: 'Editorial independence' },
  { id: 'adsense', label: 'Google AdSense' },
  { id: 'admob', label: 'Google AdMob (future)' },
  { id: 'affiliate', label: 'Affiliate disclosures (future)' },
  { id: 'standards', label: 'Ad content standards' },
  { id: 'contact', label: 'Contact us' },
]

export default function AdvertisingPolicyPage() {
  return (
    <>
      <Seo
        title="Advertising Policy"
        description="How advertising works on TitanIQ, our commitment to editorial independence, and our Google AdSense and AdMob readiness."
        path="/advertising-policy"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Advertising Policy"
        summary="How advertising is displayed on TitanIQ, and the boundary we maintain between advertising and our intelligence and predictions."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="overview" title="Overview">
          <LegalParagraph>
            TitanIQ's core product is subscription and API revenue. We are also building toward supporting
            advertising as a secondary revenue stream — Google AdSense on our web properties, and Google AdMob in a
            future TitanIQ mobile app. This policy explains how advertising will work, and the boundaries we commit
            to regardless of ad revenue.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="how-ads-display" title="How ads are displayed">
          <LegalParagraph>
            Where enabled, advertisements appear in clearly delineated placements — separate from prediction cards,
            confidence telemetry, and editorial content — and are labeled as advertising where required by applicable
            law or ad-network policy. Ads never appear inside a prediction card, confidence score, or Knowledge Graph
            visualization in a way that could be confused with TitanIQ's own intelligence output.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="sponsored-content" title="Sponsored content rules">
          <LegalParagraph>
            If TitanIQ ever publishes sponsored content (for example, a sponsored post on our{' '}
            <Link to="/blog" className="text-accent-primary hover:text-accent-primary-hover">Blog</Link>), it will be clearly labeled "Sponsored" at the point of
            publication, kept visually distinct from editorial content, and will never take the form of a
            prediction, confidence score, or model output.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="editorial-independence" title="Editorial independence">
          <LegalCallout tone="info">
            No advertiser, sponsor, or affiliate partner has any influence over TitanIQ's predictions, confidence
            scores, Knowledge Graph, or News Intelligence summaries. Our models are trained and evaluated on
            historical and live sports data only. See our{' '}
            <Link to="/editorial-policy" className="text-accent-primary hover:text-accent-primary-hover">Editorial Policy</Link> and{' '}
            <Link to="/responsible-ai" className="text-accent-primary hover:text-accent-primary-hover">Responsible AI Policy</Link> for how our intelligence
            pipeline works.
          </LegalCallout>
        </LegalSection>

        <LegalSection id="adsense" title="Google AdSense">
          <LegalParagraph>
            TitanIQ's public, logged-out pages (landing page, blog, documentation, and other informational content)
            are designed to be suitable for Google AdSense: original, substantive content; clear navigation; a
            complete privacy and cookie disclosure framework; and no content that violates AdSense program policies.
            When AdSense is enabled, ad units will be clearly marked, will not be placed on authenticated
            in-app screens where users are reviewing account or payment information, and will be disclosed in our{' '}
            <Link to="/cookies" className="text-accent-primary hover:text-accent-primary-hover">Cookie Policy</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="admob" title="Google AdMob (future)">
          <LegalParagraph>
            A native TitanIQ mobile application is on our{' '}
            <Link to="/roadmap" className="text-accent-primary hover:text-accent-primary-hover">Roadmap</Link>. Once shipped, it may integrate Google AdMob under
            the same principles described in this policy — clearly labeled placements, no influence over predictions,
            and full disclosure of any data AdMob collects for ad personalization, consistent with Google Play and
            App Store policies and applicable privacy law.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="affiliate" title="Affiliate disclosures (future)">
          <LegalParagraph>
            TitanIQ does not currently participate in affiliate marketing (including sportsbook or betting-operator
            affiliate programs). If this changes, any affiliate link will be clearly labeled at the point of use,
            and — consistent with our position as a sports intelligence platform, not a betting service — we will
            not accept affiliate arrangements that could be read as endorsing or steering users toward wagering.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="standards" title="Ad content standards">
          <LegalList
            items={[
              'No ads that are deceptive, that mimic TitanIQ UI elements, or that use manipulative design patterns.',
              'No ads promoting content prohibited under Google AdSense or AdMob program policies.',
              'Ad density is capped to preserve a readable, premium experience consistent with our design system.',
              'Users can report a concerning ad to advertising@titaniq.ai for review.',
            ]}
          />
        </LegalSection>

        <LegalSection id="contact" title="Contact us">
          <LegalParagraph>
            Questions about advertising on TitanIQ can be sent to{' '}
            <a href="mailto:advertising@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">advertising@titaniq.ai</a>.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
