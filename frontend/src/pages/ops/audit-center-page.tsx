import { ScrollText, Search } from 'lucide-react'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'

export default function AuditCenterPage() {
  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Governance"
        title="Audit Center"
        description="TitanIQ's identity domain has an audit_log_entries table used internally for record-keeping (e.g. role changes), but no admin-facing endpoint reads it back yet — so nothing here is fabricated."
      />

      <SectionCard icon={ScrollText} title="Administrative action trail">
        <BackendPendingState
          title="Timestamp, user, action, entity, before/after values, IP, device, location, status"
          description="Every field the brief asks for — who did what, to which entity, what changed, and from where — depends on a single admin-audit read endpoint over the existing audit_log_entries table. The write path already exists for at least role changes; a general-purpose write-on-every-mutation hook and a paginated read endpoint would need to be added."
          recommendedEndpoint="GET /api/v1/admin/audit?user=&action=&entity=&from=&to="
        />
      </SectionCard>

      <SectionCard icon={Search} title="Search, filtering & export">
        <BackendPendingState
          title="Audit search, filtering, and export"
          description="Depends on the read endpoint above existing first — once it does, search/filter/export are additive query parameters and a CSV/JSON export route, not a new domain."
          recommendedEndpoint="GET /api/v1/admin/audit/export"
        />
      </SectionCard>
    </div>
  )
}
