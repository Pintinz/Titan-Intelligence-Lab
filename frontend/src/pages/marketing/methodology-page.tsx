import { MarketingArticle, ArticleSection } from '@/components/layout/marketing-article'
import { Badge } from '@/components/ui/badge'

const MARKET_KINDS = [
  ['BINARY', 'Two-outcome', 'Moneyline, Match Winner, Both Teams To Score'],
  ['SPREAD', 'Point spread / handicap', 'Point Spread, Run Line, Match Handicap'],
  ['TOTAL', 'Over/under game total', 'Total Goals, Total Runs, Total Points'],
  ['TEAM_TOTAL', "One side's own total", 'Team Total Points/Runs/Goals'],
  ['PLAYER_PROP', 'Player/individual regression target', 'Player Points, Pitcher Strikeouts'],
  ['CORRECT_SCORE', 'Exact score/distribution', 'Correct Score'],
  ['RACE_TO', 'Race to N points', 'Race To 20 Points, Race To 11 Points'],
  ['SEGMENT_WINNER', 'Winner of a bounded segment', 'First Half Winner, Set Winner'],
]

/** Real methodology content sourced from docs/prediction_markets.md and docs/knowledge_graph.md
 * — replaces the "Research" nav item (a blog-style page would require fabricated posts; this
 * describes the actual, shipped prediction architecture instead). */
export default function MethodologyPage() {
  return (
    <MarketingArticle
      eyebrow="Methodology"
      title="How a TitanIQ prediction is built"
      lede="TitanIQ never uses one bespoke model per market. Every prediction market is scored by one of a small set of generic statistical predictor strategies, selected by market kind — the same architecture across all four sports."
    >
      <ArticleSection title="Market kinds">
        <p>
          Every registered market declares one of 8 market kinds — the reusable computational
          strategy it needs, not a bespoke model:
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {MARKET_KINDS.map(([kind, meaning, example]) => (
            <div key={kind} className="rounded-md border border-border-default bg-bg-elevated p-3">
              <Badge variant="accent" className="font-mono">
                {kind}
              </Badge>
              <p className="mt-2 text-text-primary">{meaning}</p>
              <p className="mt-1 text-xs text-text-muted">{example}</p>
            </div>
          ))}
        </div>
      </ArticleSection>

      <ArticleSection title="Calibration">
        <p>
          Raw model output ranks outcomes but isn&apos;t automatically trustworthy as a
          probability. Every production model is passed through one of three calibration
          strategies — Isotonic Regression, Temperature Scaling, or Platt Scaling — before its
          probabilities are published, so a 70% prediction is built to be right roughly 70% of
          the time, not just correctly ordered relative to other predictions.
        </p>
      </ArticleSection>

      <ArticleSection title="Confidence, separately from probability">
        <p>
          Confidence is a 10-factor composite — data quality, feature completeness, model
          certainty, historical accuracy, sample size adequacy, market liquidity, temporal
          relevance, ensemble agreement, calibration quality, and volatility penalty — computed
          independently of the prediction probability itself. A prediction can carry a middling
          probability with high confidence, or vice versa; the two numbers answer different
          questions.
        </p>
      </ArticleSection>

      <ArticleSection title="Explainability">
        <p>
          Where a model supports it, predictions carry a SHAP feature-attribution breakdown
          (base value plus per-feature contributions); where it doesn&apos;t, a heuristic
          explainer still surfaces the top positive and negative contributing features. Every
          prediction also carries any available knowledge-graph, news, and community-intelligence
          evidence that informed it.
        </p>
      </ArticleSection>

      <ArticleSection title="Knowledge graph">
        <p>
          Teams, players, competitions, venues, and more connect through a 47-entity-type
          knowledge graph with a temporal edge model (edges can close and be superseded, not just
          appended), queried through structured traversal — not a flat stats table.
        </p>
      </ArticleSection>
    </MarketingArticle>
  )
}
