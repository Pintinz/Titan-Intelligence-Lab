import '@/styles/landing-tokens.css'
import { LandingNav } from '@/pages/landing/landing-nav'
import { HeroSection } from '@/pages/landing/hero-section'
import { FeaturedMatchSection } from '@/pages/landing/featured-match-section'
import { IntelligenceFeedSection } from '@/pages/landing/intelligence-feed-section'
import { TodaysIntelligenceSection } from '@/pages/landing/todays-intelligence-section'
import { MultiSportSection } from '@/pages/landing/multi-sport-section'
import { NewsIntelligenceSection } from '@/pages/landing/news-intelligence-section'
import { PulseSection } from '@/pages/landing/pulse-section'
import { KnowledgeGraphSection } from '@/pages/landing/knowledge-graph-section'
import { AssistantSection } from '@/pages/landing/assistant-section'
import { LearningIntelligenceSection } from '@/pages/landing/learning-intelligence-section'
import { PlatformStatisticsSection } from '@/pages/landing/platform-statistics-section'
import { CtaSection } from '@/pages/landing/cta-section'
import { LandingFooter } from '@/pages/landing/landing-footer'
import { Hairline } from '@/pages/landing/telemetry'

/**
 * TitanIQ Landing Page — Milestone 10.1 redesign.
 *
 * Complete rebuild per the "Complete Frontend Reconstruction" brief: new visual identity
 * (Bloomberg Terminal precision + Apple HIG restraint + F1 broadcast-graphics energy), curated
 * Intelligence Cards instead of a fixture dump, and the Confidence Telemetry signature carried
 * through every section. Scoped additively (see styles/landing-tokens.css) — the authenticated
 * app's existing Milestone 10 design system is untouched.
 *
 * All sports/prediction/news/knowledge-graph data requires an authenticated session on the real
 * backend (see pages/landing/sample-data.ts's header comment) — every section below that shows
 * subject-level data is illustrative and visibly marked as such, never presented as live.
 */
export function LandingPage() {
  return (
    <div className="titan-landing min-h-screen">
      <LandingNav />
      <HeroSection />
      <Hairline />
      <FeaturedMatchSection />
      <IntelligenceFeedSection />
      <TodaysIntelligenceSection />
      <MultiSportSection />
      <Hairline />
      <NewsIntelligenceSection />
      <PulseSection />
      <KnowledgeGraphSection />
      <AssistantSection />
      <Hairline />
      <LearningIntelligenceSection />
      <PlatformStatisticsSection />
      <CtaSection />
      <LandingFooter />
    </div>
  )
}

export default LandingPage
