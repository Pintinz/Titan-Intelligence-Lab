import { motion } from 'framer-motion'
import { PredictionCard } from '@/components/domain/prediction-card'
import { KnowledgeGraphViewer } from '@/components/domain/knowledge-graph-viewer'
import type { PredictionDto, KgNodeDto, KgEdgeDto } from '@/lib/api/types'
import { transitionFast } from '@/lib/motion'

/**
 * Illustrative-but-DTO-accurate previews for the unauthenticated landing page — the real
 * PredictionCard/KnowledgeGraphViewer components, fed a literal shaped exactly like a real
 * PredictionDto/KgSubgraphDto (every field/type/range matches lib/api/types.ts), not a mockup
 * image. No live API call here since the landing page is unauthenticated and there is no public
 * per-subject prediction endpoint — clearly labeled "Illustrative" beneath each preview.
 */
const SAMPLE_PREDICTION: PredictionDto = {
  id: 'sample-prediction',
  market_id: 'football.match_result',
  model_id: 'sample-model',
  subject_ref: 'Arsenal vs. Manchester City',
  value: 'home_win',
  probability: 0.612,
  model_version: 'v14',
  status: 'published',
  generated_at: new Date(0).toISOString(),
  data_freshness: 'fresh',
  confidence: {
    overall: 0.78,
    data_quality: 0.88,
    feature_completeness: 0.82,
    model_certainty: 0.74,
    historical_accuracy: 0.71,
    sample_size_adequacy: 0.9,
    market_liquidity: 0.6,
    temporal_relevance: 0.85,
    ensemble_agreement: 0.77,
    calibration_quality: 0.8,
    volatility_penalty: 0.69,
  },
  explanation: {
    top_positive_features: [
      { feature_key: 'home_form_last_5', contribution: 0.18 },
      { feature_key: 'head_to_head_win_rate', contribution: 0.11 },
    ],
    top_negative_features: [{ feature_key: 'away_squad_rest_days', contribution: -0.07 }],
    feature_importance: { home_form_last_5: 0.18, head_to_head_win_rate: 0.11 },
    knowledge_graph_contribution: 'Home team has won 4 of the last 5 meetings at this venue.',
    news_contribution: 'No reported injuries to first-team regulars in the last 72 hours.',
    community_contribution: null,
    ai_explanation: 'Home form and historical head-to-head record are the strongest signals this window.',
    shap_explanation: {
      base_value: 0.5,
      feature_contributions: [{ feature_key: 'home_form_last_5', shap_value: 0.18 }],
    },
  },
  feature_snapshot: {},
}

const SAMPLE_CENTER: KgNodeDto = {
  id: 'team-sample',
  node_type: 'Team',
  entity_ref: 'Arsenal',
  attributes: { name: 'Arsenal' },
}

const SAMPLE_NEIGHBORS: KgNodeDto[] = [
  { id: 'player-1', node_type: 'Player', entity_ref: 'Player A', attributes: { name: 'Player A' } },
  { id: 'player-2', node_type: 'Player', entity_ref: 'Player B', attributes: { name: 'Player B' } },
  { id: 'competition-1', node_type: 'Competition', entity_ref: 'Premier League', attributes: { name: 'Premier League' } },
  { id: 'venue-1', node_type: 'Venue', entity_ref: 'Emirates Stadium', attributes: { name: 'Emirates Stadium' } },
]

const SAMPLE_EDGES: KgEdgeDto[] = [
  { edge_type: 'PLAYS_FOR', from_node_id: 'player-1', to_node_id: 'team-sample', attributes: {} },
  { edge_type: 'PLAYS_FOR', from_node_id: 'player-2', to_node_id: 'team-sample', attributes: {} },
  { edge_type: 'COMPETES_IN', from_node_id: 'team-sample', to_node_id: 'competition-1', attributes: {} },
  { edge_type: 'SCHEDULED_AT', from_node_id: 'team-sample', to_node_id: 'venue-1', attributes: {} },
]

export function FeatureShowcase() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">
          Every prediction shows its work
        </h2>
        <p className="mt-3 text-text-secondary">
          Calibrated confidence, SHAP-backed feature contributions, and the knowledge graph
          evidence behind every number — the same components signed-in users see in the
          Prediction Center and Knowledge Graph Explorer.
        </p>
      </div>

      <div className="mt-12 grid gap-8 lg:grid-cols-2">
        <motion.div whileHover={{ y: -4 }} transition={transitionFast}>
          <div className="rounded-lg shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)]">
            <PredictionCard prediction={SAMPLE_PREDICTION} />
          </div>
          <p className="mt-3 text-center text-xs text-text-muted">Illustrative preview — Prediction Center</p>
        </motion.div>
        <motion.div whileHover={{ y: -4 }} transition={transitionFast}>
          <div className="rounded-lg border border-border-default bg-bg-elevated p-4 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)]">
            <KnowledgeGraphViewer
              centerNode={SAMPLE_CENTER}
              neighbors={SAMPLE_NEIGHBORS}
              edges={SAMPLE_EDGES}
              height={340}
            />
          </div>
          <p className="mt-3 text-center text-xs text-text-muted">Illustrative preview — Knowledge Graph Explorer</p>
        </motion.div>
      </div>
    </section>
  )
}
