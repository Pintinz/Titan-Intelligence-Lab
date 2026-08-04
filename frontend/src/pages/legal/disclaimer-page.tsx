import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalCallout } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'general', label: 'General disclaimer' },
  { id: 'not-betting-advice', label: 'Not betting advice' },
  { id: 'not-financial-advice', label: 'Not financial advice' },
  { id: 'prediction-accuracy', label: 'On prediction accuracy' },
  { id: 'third-party-data', label: 'Third-party data' },
  { id: 'limitation', label: 'Limitation' },
]

export default function DisclaimerPage() {
  return (
    <>
      <Seo
        title="Disclaimer"
        description="TitanIQ predictions are informational, not betting or financial advice. Read the full disclaimer."
        path="/disclaimer"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Disclaimer"
        summary="Plain-language limits on what TitanIQ's intelligence and predictions are — and are not."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="general" title="General disclaimer">
          <LegalParagraph>
            The information provided by TitanIQ — including predictions, confidence scores, News Intelligence
            summaries, Knowledge Graph relationships, and any other output of the Service — is provided for general
            informational and entertainment purposes only. It does not constitute professional advice of any kind.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="not-betting-advice" title="Not betting advice">
          <LegalCallout tone="warning">
            TitanIQ is a sports intelligence platform, not a betting operator, tipster service, or gambling
            advisor. Nothing on TitanIQ is betting advice, and we do not encourage or facilitate wagering. If you
            choose to bet based on information from TitanIQ, that decision — and all outcomes and risks associated
            with it — is entirely your own. If gambling is affecting you negatively, resources such as your local
            responsible-gambling helpline can help.
          </LegalCallout>
        </LegalSection>

        <LegalSection id="not-financial-advice" title="Not financial advice">
          <LegalParagraph>
            TitanIQ does not provide investment, financial, or trading advice of any kind. Nothing on the platform
            should be interpreted as a recommendation to buy, sell, or hold any financial instrument.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="prediction-accuracy" title="On prediction accuracy">
          <LegalParagraph>
            Predictions and confidence scores are probabilistic estimates generated from historical and live data —
            see our <Link to="/responsible-ai" className="text-accent-primary hover:text-accent-primary-hover">Responsible AI Policy</Link> and{' '}
            <Link to="/methodology" className="text-accent-primary hover:text-accent-primary-hover">Methodology</Link> for how they're produced. Past accuracy
            does not guarantee future results, and even a high-confidence prediction can be wrong — that's the
            nature of probability applied to live sport, not a defect in the model.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="third-party-data" title="Third-party data">
          <LegalParagraph>
            TitanIQ relies on third-party providers for underlying sports data, statistics, and news. While we
            select and verify our providers, we cannot guarantee that third-party data is always complete, current,
            or error-free, and we are not responsible for errors originating from third-party sources.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="limitation" title="Limitation">
          <LegalParagraph>
            To the fullest extent permitted by law, Titan Intelligence Labs disclaims liability for any loss or
            damage arising from reliance on information provided by the Service. See the Limitation of Liability
            section of our <Link to="/terms" className="text-accent-primary hover:text-accent-primary-hover">Terms of Service</Link> for the complete legal
            terms governing this disclaimer.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
