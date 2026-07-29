import { LandingNav } from './landing/landing-nav'
import { HeroSection } from './landing/hero-section'
import { FeaturedMatchSection } from './landing/featured-match-section'
import { IntelligenceFeedSection } from './landing/intelligence-feed-section'
import { TodaysIntelligenceSection } from './landing/todays-intelligence-section'
import { MultiSportSection } from './landing/multi-sport-section'
import { NewsIntelligenceSection } from './landing/news-intelligence-section'
import { PulseSection } from './landing/pulse-section'
import { KnowledgeGraphSection } from './landing/knowledge-graph-section'
import { InsightsSection } from './landing/insights-section'
import { LearningIntelligenceSection } from './landing/learning-intelligence-section'
import { PlatformStatisticsSection } from './landing/platform-statistics-section'
import { CtaSection } from './landing/cta-section'
import { LandingFooter } from './landing/landing-footer'

export default function LandingPage() {
  return (
    <div className="min-h-svh bg-bg-primary">
      <LandingNav />
      <HeroSection />
      <TodaysIntelligenceSection />
      <FeaturedMatchSection />
      <IntelligenceFeedSection />
      <MultiSportSection />
      <NewsIntelligenceSection />
      <PulseSection />
      <KnowledgeGraphSection />
      <InsightsSection />
      <LearningIntelligenceSection />
      <PlatformStatisticsSection />
      <CtaSection />
      <LandingFooter />
    </div>
  )
}
