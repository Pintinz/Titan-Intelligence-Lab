import { Link } from 'react-router-dom'
import { MarketingArticle, ArticleSection } from '@/components/layout/marketing-article'

const MODULES = [
  ['Sports domain', 'Sport plugin architecture (football, basketball, baseball, table tennis) sharing one domain model.'],
  ['Ingestion & Knowledge Graph', 'Provider adapters, entity reconciliation, and a temporal knowledge graph of 47 entity types.'],
  ['Identity, Tenancy & Billing', 'Supabase-Auth-backed identity, organizations/teams, and a real plan/subscription/entitlement model.'],
  ['News & Community Intelligence', 'Entity/event extraction, sentiment, source reliability, and impact scoring over news and community data.'],
  ['Prediction Intelligence', 'Market registry, generic predictor strategies, calibration, confidence, and explainability engines.'],
  ['Machine Learning Platform', 'Dataset builder/registry, training pipeline, automatic model selection, SHAP explainability, drift monitoring.'],
]

/** Real architecture overview sourced from docs/architecture.md's actual section structure — not
 * a fabricated docs site. Deep API details live on the API Reference page. */
export default function DocsPage() {
  return (
    <MarketingArticle
      eyebrow="Documentation"
      title="How TitanIQ is built"
      lede="A domain-driven, bounded-context architecture — one shared sport-plugin core, extended by ingestion, knowledge graph, intelligence, and prediction modules."
    >
      <ArticleSection title="Modules">
        <div className="grid gap-3 sm:grid-cols-2">
          {MODULES.map(([name, desc]) => (
            <div key={name} className="rounded-md border border-border-default bg-bg-elevated p-4">
              <p className="font-medium text-text-primary">{name}</p>
              <p className="mt-1 text-xs text-text-muted">{desc}</p>
            </div>
          ))}
        </div>
      </ArticleSection>

      <ArticleSection title="Looking for endpoint details?">
        <p>
          See the <Link to="/api-reference" className="text-accent-primary hover:underline">API Reference</Link> for
          route groups, or the <Link to="/methodology" className="text-accent-primary hover:underline">Methodology</Link> page
          for how predictions themselves are computed.
        </p>
      </ArticleSection>
    </MarketingArticle>
  )
}
