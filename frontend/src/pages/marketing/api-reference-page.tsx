import { MarketingArticle, ArticleSection } from '@/components/layout/marketing-article'

/** Real route-group table sourced from docs/api_specification.md §2 — every prefix listed here
 * is a real, deployed FastAPI router, not a planned/aspirational one. */
const ROUTE_GROUPS = [
  ['Identity', '/api/v1/auth, /api/v1/users', 'Delegates to Supabase Auth'],
  ['Sports', '/api/v1/sports, /api/v1/competitions, /api/v1/teams, /api/v1/players, /api/v1/fixtures', 'Read-heavy, cached'],
  ['Predictions', '/api/v1/predictions, /api/v1/markets', 'Includes confidence + explanation payload inline'],
  ['Knowledge Graph', '/api/v1/graph', 'Relationship/similarity/context/traversal queries'],
  ['Analytics', '/api/v1/analytics', 'Dashboards, comparative analysis'],
  ['Billing', '/api/v1/billing', 'Subscriptions, plans, usage counters'],
  ['Intelligence', '/api/v1/intelligence', 'News + community intelligence, read-only to clients'],
  ['Admin', '/api/v1/admin/*', 'Role-gated'],
]

export default function ApiReferencePage() {
  return (
    <MarketingArticle
      eyebrow="API Reference"
      title="Route groups"
      lede="TitanIQ's backend is a single FastAPI service organized into module-scoped route groups. Every prediction response carries its confidence and explanation payload inline — no separate round-trip needed."
    >
      <ArticleSection title="Modules">
        <div className="overflow-x-auto rounded-md border border-border-default">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border-default bg-bg-elevated text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-4 py-2">Module</th>
                <th className="px-4 py-2">Prefix</th>
                <th className="px-4 py-2">Notes</th>
              </tr>
            </thead>
            <tbody>
              {ROUTE_GROUPS.map(([module, prefix, notes]) => (
                <tr key={module} className="border-b border-border-subtle last:border-0">
                  <td className="px-4 py-2 text-text-primary">{module}</td>
                  <td className="px-4 py-2 font-mono text-xs text-text-secondary">{prefix}</td>
                  <td className="px-4 py-2 text-text-muted">{notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ArticleSection>

      <ArticleSection title="Authentication">
        <p>
          Every non-public endpoint accepts a Supabase Auth JWT as a Bearer token. Role-gated
          routes (Admin, ML Platform) additionally require an administrator-tier platform role,
          enforced at both the API and database (RLS) layers.
        </p>
      </ArticleSection>
    </MarketingArticle>
  )
}
