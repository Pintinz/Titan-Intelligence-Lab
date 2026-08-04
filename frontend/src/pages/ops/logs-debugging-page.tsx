import { TerminalSquare, FileSearch } from 'lucide-react'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'

export default function LogsDebuggingPage() {
  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Diagnostics"
        title="Logs & Debugging"
        description="The backend logs to stdout/stderr in its hosting environment today — there is no log-aggregation service or admin-facing log query endpoint, so this page names the gap instead of faking log lines."
      />

      <SectionCard icon={TerminalSquare} title="Application, API, and pipeline logs">
        <BackendPendingState
          title="Application logs, API logs, provider logs, ML logs, prediction logs, background job logs, realtime logs"
          description="Each subsystem already produces structured log output at runtime, but nothing forwards it into a queryable store the Operations Center could read. Error and warning levels are not currently separated from an admin-consumable feed."
          recommendedEndpoint="GET /api/v1/admin/logs?source=&level=&from=&to="
        />
      </SectionCard>

      <SectionCard icon={FileSearch} title="Search, filtering & download">
        <BackendPendingState
          title="Live log search, filtering, and download"
          description="Depends on a log-aggregation backend existing first — most realistically an external sink (e.g. hosted logging) with an admin proxy endpoint, rather than storing raw logs in the primary database."
          recommendedEndpoint="GET /api/v1/admin/logs/export"
        />
      </SectionCard>
    </div>
  )
}
