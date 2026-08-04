/**
 * Single source of truth for the public-facing (logged-out) site navigation — the mega-menu
 * header and the enterprise footer both read from this file so a link only ever needs updating
 * in one place. Distinct from `nav-config.ts`, which drives the authenticated `/app` sidebar.
 */

export interface MegaMenuLink {
  label: string
  href: string
  description?: string
}

export interface MegaMenuColumn {
  label: string
  links: MegaMenuLink[]
}

export const HEADER_MENUS: MegaMenuColumn[] = [
  {
    label: 'Platform',
    links: [
      { label: 'Dashboard', href: '/app', description: 'Your intelligence workspace' },
      { label: 'Football', href: '/app/football', description: 'Live match & prediction intelligence' },
      { label: 'Basketball', href: '/app/basketball', description: 'Live match & prediction intelligence' },
      { label: 'Baseball', href: '/app/baseball', description: 'Live match & prediction intelligence' },
      { label: 'Table Tennis', href: '/app/table-tennis', description: 'Live match & prediction intelligence' },
      { label: 'Knowledge Graph', href: '/app/graph', description: 'Entities, relationships, evidence' },
      { label: 'TitanIQ Insights', href: '/app/insights', description: 'Cross-sport analytics & trends' },
      { label: 'Learning Intelligence', href: '/app/learning', description: 'How the model retrains itself' },
    ],
  },
  {
    label: 'Resources',
    links: [
      { label: 'Documentation', href: '/docs', description: 'Guides for using the platform' },
      { label: 'Developer Portal', href: '/developers', description: 'Build on the TitanIQ API' },
      { label: 'API Reference', href: '/api-reference', description: 'Endpoints, schemas, auth' },
      { label: 'Methodology', href: '/methodology', description: 'How predictions are calculated' },
      { label: 'Blog', href: '/blog', description: 'Product updates & intelligence notes' },
      { label: 'Release Notes', href: '/release-notes', description: "What's shipped, milestone by milestone" },
      { label: 'Roadmap', href: '/roadmap', description: "Where TitanIQ is headed" },
    ],
  },
  {
    label: 'Company',
    links: [
      { label: 'About', href: '/about', description: 'Our mission and principles' },
      { label: 'Careers', href: '/careers', description: 'Join Titan Intelligence Labs' },
      { label: 'Contact', href: '/contact', description: 'Talk to our team' },
      { label: 'Trust Center', href: '/trust-center', description: 'Security, privacy & compliance' },
      { label: 'Partners', href: '/partners', description: 'Data, news & technology partnerships' },
      { label: 'Press Kit', href: '/press-kit', description: 'Boilerplate, facts & media contact' },
      { label: 'Brand Assets', href: '/brand-assets', description: 'Logo, color & type guidelines' },
    ],
  },
]

/**
 * Deliberately a small subset of the full site map — the footer's job is quick orientation, not
 * an exhaustive sitemap. Everything not listed here (Developer Portal, Release Notes, Roadmap,
 * Trust Center, Security/Editorial/Advertising/Copyright/DMCA/Acceptable Use/GDPR/CCPA policies,
 * Licenses, Brand Assets, Press Kit, Partners, News Intelligence, Knowledge Graph, Insights,
 * Learning Intelligence, Support, Status) still exists and is reachable via the header mega-menu,
 * the Trust Center's policy index, or the About page — never removed, just not duplicated here.
 */
export const FOOTER_COLUMNS: MegaMenuColumn[] = [
  {
    label: 'Platform',
    links: [
      { label: 'Dashboard', href: '/app' },
      { label: 'Football Intelligence', href: '/app/football' },
      { label: 'Basketball Intelligence', href: '/app/basketball' },
      { label: 'Baseball Intelligence', href: '/app/baseball' },
      { label: 'Table Tennis Intelligence', href: '/app/table-tennis' },
      { label: 'News Intelligence', href: '/app/news' },
    ],
  },
  {
    label: 'Resources',
    links: [
      { label: 'Documentation', href: '/docs' },
      { label: 'API Reference', href: '/api-reference' },
      { label: 'Methodology', href: '/methodology' },
      { label: 'Pricing', href: '/pricing' },
      { label: 'FAQ', href: '/faq' },
    ],
  },
  {
    label: 'Company',
    links: [
      { label: 'About TitanIQ', href: '/about' },
      { label: 'Contact Us', href: '/contact' },
      { label: 'Careers', href: '/careers' },
    ],
  },
  {
    label: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '/privacy' },
      { label: 'Terms of Service', href: '/terms' },
      { label: 'Cookie Policy', href: '/cookies' },
      { label: 'Responsible AI Policy', href: '/responsible-ai' },
      { label: 'Disclaimer', href: '/disclaimer' },
    ],
  },
]

/** Brief explicitly caps this to Facebook / Instagram / X — no LinkedIn, GitHub, or YouTube. */
export const SOCIAL_LINKS = [
  { label: 'Facebook', href: 'https://facebook.com/titaniq' },
  { label: 'Instagram', href: 'https://instagram.com/titaniq' },
  { label: 'X', href: 'https://x.com/titaniq' },
]

export const PLATFORM_VERSION = 'v10.3.0'
