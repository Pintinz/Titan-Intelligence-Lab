import { SiteHeader } from '@/components/layout/site-header'
import { SiteFooter } from '@/components/layout/site-footer'
import { Seo } from '@/components/seo/seo'
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

export default function LandingPage() {
  return (
    <div className="min-h-svh bg-bg-primary">
      <Seo
        title="TitanIQ — Sports Intelligence Beyond Prediction"
        description="TitanIQ transforms live sports data, structured intelligence, news, and community signals into explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis."
        path="/"
      />
      <SiteHeader />
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
      <SiteFooter />
    </div>
  )
}
