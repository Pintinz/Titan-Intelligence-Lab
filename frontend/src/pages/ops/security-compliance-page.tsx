import { ShieldCheck, LockKeyhole, Radar, ShieldAlert } from 'lucide-react'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'

export default function SecurityCompliancePage() {
  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Security"
        title="Security & Compliance"
        description="No security-monitoring domain exists in the backend yet — this page is fully honest about that rather than fabricating a dashboard. RBAC itself is real and enforced on every admin endpoint (see Users & Roles); what's missing is observability into it."
      />

      <SectionCard icon={LockKeyhole} title="Identity & credential security">
        <BackendPendingState
          title="JWT health, secret rotation, MFA status, and API key security"
          description="Supabase manages JWT signing and MFA enrollment directly — TitanIQ's backend has no admin-facing endpoint to surface JWT signing-key age, secret rotation history, per-user MFA enrollment status, or a masked view of API credential health."
          recommendedEndpoint="GET /api/v1/admin/security/jwt-health · GET /api/v1/admin/security/mfa-status"
        />
      </SectionCard>

      <SectionCard icon={Radar} title="Threat & access monitoring">
        <BackendPendingState
          title="Threat detection, IP monitoring, rate limiting, blocked requests"
          description="Rate limiting exists at the infrastructure layer but is not exposed for inspection. There is no anomaly/threat-detection service, no IP reputation tracking, and no admin view of blocked or rate-limited requests."
          recommendedEndpoint="GET /api/v1/admin/security/blocked-requests · GET /api/v1/admin/security/rate-limit-status"
        />
      </SectionCard>

      <SectionCard icon={ShieldAlert} title="Failed logins & security timeline">
        <BackendPendingState
          title="Failed login tracking and a chronological security event timeline"
          description="Login attempts are handled by Supabase Auth and are not mirrored into an admin-queryable timeline in TitanIQ's own backend."
          recommendedEndpoint="GET /api/v1/admin/security/failed-logins · GET /api/v1/admin/security/timeline"
        />
      </SectionCard>

      <SectionCard icon={ShieldCheck} title="Compliance status (GDPR / CCPA)">
        <BackendPendingState
          title="Automated GDPR/CCPA compliance status"
          description="TitanIQ's Trust Center publishes the platform's privacy policy and data-subject-request process to end users, but there is no backend service tracking data-request fulfillment status, retention-policy enforcement, or a machine-readable compliance scorecard."
          recommendedEndpoint="GET /api/v1/admin/compliance/status"
        />
      </SectionCard>
    </div>
  )
}
