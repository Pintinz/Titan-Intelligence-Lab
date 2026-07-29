import { HeroSection } from '@/pages/landing/hero-section'
import { LandingNav } from '@/pages/landing/landing-nav'
import { LiveIntelligenceSection } from '@/pages/landing/live-intelligence-section'
import { PredictionsShowcaseSection } from '@/pages/landing/predictions-showcase-section'
import { FeaturedMatchSection } from '@/pages/landing/featured-match-section'
import { SportsExplorerSection } from '@/pages/landing/sports-explorer-section'
import { CompetitionShowcaseSection } from '@/pages/landing/competition-showcase-section'
import { TeamSpotlightSection } from '@/pages/landing/team-spotlight-section'
import { PlayerSpotlightSection } from '@/pages/landing/player-spotlight-section'
import { KnowledgeGraphPreviewSection } from '@/pages/landing/knowledge-graph-preview-section'
import { NewsIntelligenceSection } from '@/pages/landing/news-intelligence-section'
import { ModelIntelligenceSection } from '@/pages/landing/model-intelligence-section'
import { ProductWalkthroughSection } from '@/pages/landing/product-walkthrough-section'
import { AudienceSection } from '@/pages/landing/audience-section'
import { FeatureShowcase } from '@/pages/landing/feature-showcase'
import { ArchitectureCallouts } from '@/pages/landing/architecture-callouts'
import { PlatformStatisticsSection } from '@/pages/landing/platform-statistics-section'
import { PricingSection } from '@/pages/landing/pricing-section'
import { FaqSection } from '@/pages/landing/faq-section'

export function LandingPage() {
  return (
    <>
      <HeroSection />
      <LandingNav />
      <LiveIntelligenceSection />
      <PredictionsShowcaseSection />
      <FeaturedMatchSection />
      <SportsExplorerSection />
      <CompetitionShowcaseSection />
      <TeamSpotlightSection />
      <PlayerSpotlightSection />
      <KnowledgeGraphPreviewSection />
      <NewsIntelligenceSection />
      <ModelIntelligenceSection />
      <ProductWalkthroughSection />
      <AudienceSection />
      <FeatureShowcase />
      <PlatformStatisticsSection />
      <ArchitectureCallouts />
      <PricingSection />
      <FaqSection />
    </>
  )
}

export default LandingPage
