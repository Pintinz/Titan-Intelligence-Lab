import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList } from '@/components/marketing/legal-layout'
import { cn } from '@/lib/cn'

const TOC = [
  { id: 'base-url', label: 'Base URL & versioning' },
  { id: 'authentication', label: 'Authentication' },
  { id: 'sports', label: 'Sports resources' },
  { id: 'predictions', label: 'Predictions' },
  { id: 'errors', label: 'Error format' },
  { id: 'rate-limits', label: 'Rate limits' },
]

const METHOD_STYLE: Record<string, string> = {
  GET: 'bg-info-muted text-info',
  POST: 'bg-success-muted text-success',
}

function EndpointTable({ rows }: { rows: { method: 'GET' | 'POST'; path: string; description: string }[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full min-w-[560px] text-left text-sm">
        <tbody className="divide-y divide-border-subtle">
          {rows.map((row) => (
            <tr key={row.path + row.method}>
              <td className="whitespace-nowrap px-4 py-3">
                <span className={cn('rounded px-1.5 py-0.5 font-mono text-xs font-semibold', METHOD_STYLE[row.method])}>{row.method}</span>
              </td>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-text-primary">{row.path}</td>
              <td className="px-4 py-3 text-text-secondary">{row.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ApiReferencePage() {
  return (
    <>
      <Seo
        title="API Reference"
        description="TitanIQ REST API reference — authentication, sports resources, predictions, error format, and rate limits."
        path="/api-reference"
      />
      <LegalPageLayout
        eyebrow="Developers"
        title="API Reference"
        summary="A REST API over TitanIQ's sports resources and predictions — the same contract our own application is built on."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="base-url" title="Base URL & versioning">
          <LegalParagraph>
            All requests are made to <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">https://api.titaniq.ai</code>. The API is
            versioned in the path — the current stable version is <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">v1</code>.
            Breaking changes are only introduced in a new version, announced on{' '}
            <Link to="/release-notes" className="text-accent-primary hover:text-accent-primary-hover">Release Notes</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="authentication" title="Authentication">
          <LegalParagraph>
            Authenticate by sending an API key as a bearer token. Generate and rotate keys from your account
            settings once signed in.
          </LegalParagraph>
          <div className="overflow-hidden rounded-lg border border-border-default bg-bg-primary">
            <pre className="overflow-x-auto p-4 text-sm">
              <code className="font-mono text-text-primary">Authorization: Bearer YOUR_API_KEY</code>
            </pre>
          </div>
        </LegalSection>

        <LegalSection id="sports" title="Sports resources">
          <LegalParagraph>
            Every sport (<code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">football</code>,{' '}
            <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">basketball</code>,{' '}
            <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">baseball</code>,{' '}
            <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">table-tennis</code>) exposes the same resource shape:
          </LegalParagraph>
          <EndpointTable
            rows={[
              { method: 'GET', path: '/api/v1/sports/{sport}/fixtures', description: 'List fixtures for a sport, filterable by status and date.' },
              { method: 'GET', path: '/api/v1/sports/fixtures/{fixtureId}', description: 'Get a single fixture with full match intelligence.' },
              { method: 'GET', path: '/api/v1/sports/{sport}/teams', description: 'List teams for a sport.' },
              { method: 'GET', path: '/api/v1/sports/teams/{teamId}', description: 'Get a team, including recent form.' },
              { method: 'GET', path: '/api/v1/sports/teams/{teamId}/players', description: 'List a team\'s players.' },
              { method: 'GET', path: '/api/v1/sports/{sport}/competitions', description: 'List competitions for a sport.' },
              { method: 'GET', path: '/api/v1/sports/competitions/{competitionId}/standings', description: 'Get current standings for a competition.' },
            ]}
          />
        </LegalSection>

        <LegalSection id="predictions" title="Predictions">
          <EndpointTable
            rows={[
              { method: 'GET', path: '/api/v1/predictions', description: 'List predictions, filterable by market.' },
              { method: 'POST', path: '/api/v1/predictions/generate', description: 'Generate a fresh prediction for a given market (Pro/Enterprise).' },
              { method: 'POST', path: '/api/v1/predictions/compare', description: 'Compare multiple predictions side by side.' },
            ]}
          />
          <LegalParagraph className="mt-3">
            Every prediction response includes its confidence score and the evidence fields behind it — see{' '}
            <Link to="/methodology" className="text-accent-primary hover:text-accent-primary-hover">Methodology</Link> for what those fields mean.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="errors" title="Error format">
          <LegalParagraph>Errors return a consistent JSON body with an HTTP status code and a machine-readable code:</LegalParagraph>
          <div className="overflow-hidden rounded-lg border border-border-default bg-bg-primary">
            <pre className="overflow-x-auto p-4 text-sm">
              <code className="font-mono text-text-primary">{`{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "You have exceeded your plan's request rate limit."
  }
}`}</code>
            </pre>
          </div>
        </LegalSection>

        <LegalSection id="rate-limits" title="Rate limits">
          <LegalList
            items={[
              'Free: 60 requests/minute',
              'Pro: 300 requests/minute',
              'Enterprise: custom limits by agreement',
            ]}
          />
          <LegalParagraph className="mt-3">
            Every response includes <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">X-RateLimit-Remaining</code> and{' '}
            <code className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono text-xs">X-RateLimit-Reset</code> headers. Usage beyond documented
            limits is governed by our{' '}
            <Link to="/acceptable-use" className="text-accent-primary hover:text-accent-primary-hover">Acceptable Use Policy</Link>.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
