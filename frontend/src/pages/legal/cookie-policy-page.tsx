import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { LegalPageLayout, LegalSection, LegalParagraph, LegalList } from '@/components/marketing/legal-layout'

const TOC = [
  { id: 'what-are-cookies', label: 'What are cookies' },
  { id: 'essential', label: 'Essential cookies' },
  { id: 'analytics', label: 'Analytics cookies' },
  { id: 'preferences', label: 'Preference cookies' },
  { id: 'marketing', label: 'Marketing cookies (future)' },
  { id: 'third-party', label: 'Third-party cookies' },
  { id: 'managing', label: 'Managing your preferences' },
  { id: 'retention', label: 'Retention periods' },
  { id: 'updates', label: 'Updates to this policy' },
]

const CATEGORIES = [
  {
    id: 'essential',
    name: 'Essential',
    consent: 'Always on',
    purpose: 'Authentication, session management, security (CSRF protection), and load balancing.',
    retention: 'Session, or up to 30 days for "remember me."',
  },
  {
    id: 'analytics',
    name: 'Analytics',
    consent: 'Opt-in',
    purpose: 'Understand feature usage and page performance in aggregate to improve the product.',
    retention: 'Up to 13 months.',
  },
  {
    id: 'preferences',
    name: 'Preferences',
    consent: 'Opt-in',
    purpose: 'Remember display settings such as theme, default sport, and dismissed prompts.',
    retention: 'Up to 12 months.',
  },
  {
    id: 'marketing',
    name: 'Marketing (future)',
    consent: 'Opt-in, not yet active',
    purpose: 'Will support Google AdSense ad delivery and measurement once advertising is enabled.',
    retention: 'Governed by Google, disclosed here before activation.',
  },
]

export default function CookiePolicyPage() {
  return (
    <>
      <Seo
        title="Cookie Policy"
        description="What cookies TitanIQ uses, why, and how to manage your consent."
        path="/cookies"
      />
      <LegalPageLayout
        eyebrow="Legal"
        title="Cookie Policy"
        summary="This policy explains what cookies and similar technologies TitanIQ uses, why, and how you can control them."
        lastUpdated="July 29, 2026"
        toc={TOC}
      >
        <LegalSection id="what-are-cookies" title="What are cookies">
          <LegalParagraph>
            Cookies are small text files stored on your device that let a website remember information about your
            visit. We use cookies and similar technologies (such as local storage) to run the Service, remember
            your preferences, and — where you consent — understand how the Service is used.
          </LegalParagraph>
        </LegalSection>

        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-bg-secondary/60 text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Consent</th>
                <th className="px-4 py-3 font-medium">Purpose</th>
                <th className="px-4 py-3 font-medium">Retention</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {CATEGORIES.map((c) => (
                <tr key={c.id} id={c.id === 'marketing' ? 'marketing' : undefined}>
                  <td className="px-4 py-3 font-medium text-text-primary">{c.name}</td>
                  <td className="px-4 py-3 text-text-secondary">{c.consent}</td>
                  <td className="px-4 py-3 text-text-secondary">{c.purpose}</td>
                  <td className="px-4 py-3 text-text-secondary">{c.retention}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <LegalSection id="essential" title="Essential cookies">
          <LegalParagraph>
            These cookies are required for the Service to function — they keep you signed in, protect against
            cross-site request forgery, and route traffic reliably. Because they're strictly necessary, they can't
            be disabled through a consent banner; you can block them in your browser, but the Service will not work
            correctly without them.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="analytics" title="Analytics cookies">
          <LegalParagraph>
            With your consent, we use analytics cookies to understand aggregate usage patterns — which features are
            used, how pages perform, and where errors occur — so we can improve the Service. Analytics data is used
            in aggregate and is not sold.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="preferences" title="Preference cookies">
          <LegalParagraph>
            These remember choices you make, like light/dark theme or a default Sport Intelligence Center, so you
            don't have to reset them on every visit.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="marketing" title="Marketing cookies (future)">
          <LegalParagraph>
            TitanIQ's public pages are built to support Google AdSense, and a future TitanIQ mobile app is expected
            to support Google AdMob. Advertising cookies are <strong className="text-text-primary">not currently active</strong>. Before they are
            enabled, this policy and our consent banner will be updated to disclose the specific advertising
            cookies in use and to obtain your opt-in consent where required, consistent with our{' '}
            <Link to="/advertising-policy" className="text-accent-primary hover:text-accent-primary-hover">Advertising Policy</Link>.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="third-party" title="Third-party cookies">
          <LegalParagraph>
            Some functionality relies on third-party providers (for example, our authentication and analytics
            infrastructure), which may set their own cookies subject to their respective privacy policies. We
            select providers that meet our security and privacy standards.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="managing" title="Managing your preferences">
          <LegalList
            items={[
              'On your first visit, a consent banner lets you accept or customize non-essential cookie categories.',
              'You can change your preferences at any time from the cookie settings link in the site footer.',
              'You can also block or delete cookies through your browser settings, though this may affect functionality.',
              'Opting out of analytics does not affect essential cookies required to keep you signed in.',
            ]}
          />
        </LegalSection>

        <LegalSection id="retention" title="Retention periods">
          <LegalParagraph>
            Retention periods per category are listed in the table above. We periodically review these periods to
            ensure we retain cookie data no longer than necessary for its purpose.
          </LegalParagraph>
        </LegalSection>

        <LegalSection id="updates" title="Updates to this policy">
          <LegalParagraph>
            We'll update this page and the "Last updated" date whenever our cookie usage changes — most notably
            when advertising cookies are activated.
          </LegalParagraph>
        </LegalSection>
      </LegalPageLayout>
    </>
  )
}
