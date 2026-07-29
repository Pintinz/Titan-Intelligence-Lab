import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const FAQ = [
  {
    q: 'How are predictions calibrated?',
    a: 'Every production model runs through Isotonic Regression, Temperature Scaling, or Platt Scaling before its probabilities are trusted — the Prediction Center shows whether a prediction has a SHAP explanation or falls back to the heuristic explainer.',
  },
  {
    q: 'What does the Confidence score mean?',
    a: 'A 10-factor composite (data quality, feature completeness, model certainty, historical accuracy, sample size, market liquidity, temporal relevance, ensemble agreement, calibration quality, volatility penalty) — distinct from the prediction probability itself.',
  },
  {
    q: 'Why can\'t I search the Knowledge Graph by free text?',
    a: 'The Knowledge Graph module supports structured traversal and named retrieval queries, not fuzzy text search — that capability doesn\'t exist yet. Browse by entity type in the Knowledge Graph Explorer instead.',
  },
  {
    q: 'Who can see the Admin Center and ML Platform pages?',
    a: 'Administrator role and above — the same RBAC ladder enforced at both the API and database layers (docs/security.md).',
  },
]

export default function HelpCenterPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Help Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Help Center</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Frequently asked questions</CardTitle>
        </CardHeader>
        <CardContent>
          <Accordion type="single" collapsible>
            {FAQ.map((item, i) => (
              <AccordionItem key={i} value={`item-${i}`}>
                <AccordionTrigger>{item.q}</AccordionTrigger>
                <AccordionContent>{item.a}</AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>
    </div>
  )
}
