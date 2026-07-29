import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { SPORT_OPTIONS } from '@/lib/api/sports'

/** Same honest facts as the in-app Help Center (pages/help/help-center-page.tsx), reworded for a
 * pre-signup audience — no new claims invented for marketing purposes. */
const FAQ = [
  {
    q: 'Which sports does TitanIQ cover?',
    a: `${SPORT_OPTIONS.map((s) => s.label).join(', ')} today, with the same prediction, calibration, and knowledge-graph architecture behind each.`,
  },
  {
    q: 'How are predictions calibrated?',
    a: 'Every production model is run through Isotonic Regression, Temperature Scaling, or Platt Scaling before its probabilities are trusted — a 70% prediction is built to win roughly 70% of the time, not just rank outcomes in the right order.',
  },
  {
    q: 'What does the confidence score mean?',
    a: 'A 10-factor composite — data quality, feature completeness, model certainty, historical accuracy, sample size, market liquidity, temporal relevance, ensemble agreement, calibration quality, and volatility penalty — distinct from the prediction probability itself.',
  },
  {
    q: 'Is this betting advice?',
    a: 'No. TitanIQ produces probabilistic sports-outcome estimates for analysis and research — it is not a sportsbook and does not provide betting or financial advice.',
  },
]

export function FaqSection() {
  return (
    <section id="faq" className="mx-auto max-w-3xl px-6 py-20">
      <h2 className="text-center font-display text-3xl font-semibold text-text-primary">
        Frequently asked questions
      </h2>
      <div className="mt-10">
        <Accordion type="single" collapsible>
          {FAQ.map((item, i) => (
            <AccordionItem key={i} value={`item-${i}`}>
              <AccordionTrigger>{item.q}</AccordionTrigger>
              <AccordionContent>{item.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  )
}
